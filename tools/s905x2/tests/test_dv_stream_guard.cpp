#include "AMLDVStreamGuard.h"
#include <cassert>
#include <vector>
#include <utility>

static std::vector<unsigned char> output;
static std::vector<std::pair<unsigned long long,size_t>> timestamps;
static int calls=0;
static bool stalled=true;
static int init(codec_para_t*) { return 0; }
static int write_data(codec_para_t*,void*b,int n) {
    if(stalled && ++calls%11==0) { errno=EAGAIN;return -1; }
    if(stalled && n>137)n=137;
    auto p=static_cast<unsigned char*>(b);output.insert(output.end(),p,p+n);return n;
}
static int pts(codec_para_t*,unsigned long long value) { timestamps.emplace_back(value,output.size());return 0; }
static void nal(std::vector<unsigned char>&v,int type,int inner,int length) {
    v.insert(v.end(),{0,0,0,1,static_cast<unsigned char>(type<<1),1});
    if(type==63)v.insert(v.end(),{static_cast<unsigned char>(inner<<1),1});
    v.insert(v.end(),length-(type==63?4:2),0x55);
}
int main() {
    codec_para_t c{true,true,VFORMAT_HEVC};AMLDVStreamGuard guard;
    assert(guard.Init(&c,init,write_data,init,pts)==0);
    std::vector<unsigned char> first,later,expected;
    nal(first,32,0,25);nal(first,20,0,1024);size_t insertion=first.size();nal(first,63,0,42);
    nal(later,1,0,300);nal(later,63,32,26);nal(later,63,33,62);nal(later,63,34,9);nal(later,63,20,600);
    expected=first;expected.insert(expected.end(),later.begin(),later.end());
    size_t offset=0;
    for(auto* packet:{&first,&later}) {
        assert(guard.CheckinPts(&c,offset)==0);size_t n=0;
        while(n<packet->size()) {
            int r=guard.Write(&c,packet->data()+n,packet->size()-n);
            if(r<0){assert(errno==EAGAIN);continue;}assert(r>0);n+=r;
        }
        offset+=packet->size();
    }
    // Drain a pending replay through normal input calls, exercising EAGAIN.
    stalled=false;std::vector<unsigned char> extra;nal(extra,1,0,60);
    assert(guard.CheckinPts(&c,offset)==0);assert(guard.Write(&c,extra.data(),extra.size())==static_cast<int>(extra.size()));expected.insert(expected.end(),extra.begin(),extra.end());
    assert(output.size()==expected.size()+109);
    assert(std::equal(expected.begin(),expected.begin()+insertion,output.begin()));
    assert(std::equal(expected.begin()+insertion,expected.end(),output.begin()+insertion+109));
    for(auto t:timestamps)assert(t.second==t.first+(t.first>insertion?109:0));
    // Seek reset must refeed the same movie's headers.
    assert(guard.Reset(&c)==0);size_t before=output.size();
    assert(guard.Write(&c,first.data(),first.size())==static_cast<int>(first.size()));assert(output.size()==before+first.size()+109);
    // HDR/single-layer streams bypass the queue; new sessions discard old headers.
    assert(guard.Close(&c,init)==0);c.dv_enable=false;assert(guard.Init(&c,init,write_data,init,pts)==0);
    before=output.size();assert(guard.Write(&c,first.data(),first.size())==static_cast<int>(first.size()));assert(output.size()==before+first.size());
    c.dv_enable=true;assert(guard.Init(&c,init,write_data,init,pts)==0);before=output.size();assert(guard.Write(&c,first.data(),first.size())==static_cast<int>(first.size()));assert(output.size()==before);
    guard.Close(&c,init);
    puts("PASS: native DV cold start, ordered PTS replay, backpressure, seek, HDR bypass, session isolation");
}
