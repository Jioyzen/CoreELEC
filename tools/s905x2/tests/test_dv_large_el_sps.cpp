#include "AMLDVStreamGuard.h"
#include <cassert>
#include <vector>
#include <cstdio>

static std::vector<unsigned char> output;
static int init(codec_para_t*) { return 0; }
static int write_data(codec_para_t*, void* data, int size)
{
  auto bytes = static_cast<unsigned char*>(data);
  output.insert(output.end(), bytes, bytes + size);
  return size;
}
static int pts(codec_para_t*, unsigned long long) { return 0; }
static void nal(std::vector<unsigned char>& stream, int inner, size_t size)
{
  stream.insert(stream.end(), {0, 0, 0, 1, 126, 1,
                              static_cast<unsigned char>(inner << 1), 1});
  stream.insert(stream.end(), size - 4, 0x55);
}
int main()
{
  codec_para_t codec{true, true, VFORMAT_HEVC};
  AMLDVStreamGuard guard;
  assert(guard.Init(&codec, init, write_data, init, pts) == 0);
  std::vector<unsigned char> vps, rest;
  nal(vps, 32, 34);
  nal(rest, 33, 671);
  nal(rest, 34, 11);
  nal(rest, 19, 64); // Delimit PPS so all three parameter sets are complete.
  assert(guard.Write(&codec, vps.data(), vps.size()) == static_cast<int>(vps.size()));
  // Split the oversized SPS over several input writes.
  for (size_t offset = 0; offset < rest.size();)
  {
    size_t length = std::min<size_t>(47, rest.size() - offset);
    assert(guard.Write(&codec, rest.data() + offset, length) == static_cast<int>(length));
    offset += length;
  }
  const size_t injection = 34 + 671 + 11 + 12;
  assert(output.size() == vps.size() + rest.size() + injection);
  assert(guard.Reset(&codec) == 0);
  size_t before = output.size();
  assert(guard.Write(&codec, vps.data(), vps.size()) == static_cast<int>(vps.size()));
  assert(output.size() == before + vps.size() + injection);
  assert(guard.Close(&codec, init) == 0);
  puts("PASS: 671-byte EL SPS, fragmented input, cold start and seek replay");
}
