/* Exercise the actual patched map/device helpers with ASAN and allocation failures. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CUSTOM_NAME_LEN 64
#define GFP_KERNEL 0
#define BUS_ISA 0x10
#define REP_DELAY 0
#define REP_PERIOD 1
#define spin_lock_irqsave(lock, flags) ((void)(lock), (flags)=0)
#define spin_unlock_irqrestore(lock, flags) ((void)(lock), (void)(flags))
struct input_id { unsigned short bustype,vendor,product,version; };
struct input_dev {
 struct input_id id;
 const char *name,*phys;
 struct { void *parent; } dev;
 unsigned int rep[2];
 bool configured;
};
struct meson_ir_dev { unsigned int input_dev_num; struct input_dev **input_devs; int keylock; };
struct meson_ir_map_tab_list { struct { struct input_id id; char custom_name[CUSTOM_NAME_LEN]; } tab; };
struct meson_ir_chip { struct meson_ir_dev *r_dev; void *dev; int dev_no; };
static struct input_dev *managed[128];static size_t managed_count;
enum {FAIL_NONE,FAIL_ARRAY,FAIL_INPUT,FAIL_NAME,FAIL_REGISTER};static int failure;
static void *kmalloc_array(size_t n,size_t size,int flags) {
 (void)flags;if(failure==FAIL_ARRAY)return NULL;return malloc(n*size);
}
static void kfree(void *p) {free(p);}
static struct input_dev *devm_input_allocate_device(void *dev) {
 (void)dev;if(failure==FAIL_INPUT)return NULL;
 assert(managed_count<128);struct input_dev *p=calloc(1,sizeof(*p));assert(p);managed[managed_count++]=p;return p;
}
static char *devm_kasprintf(void *dev,int flags,const char *format,...) {
 (void)dev;(void)flags;if(failure==FAIL_NAME)return NULL;
 char s[64];va_list args;va_start(args,format);vsnprintf(s,sizeof(s),format,args);va_end(args);
 char *p=malloc(strlen(s)+1);assert(p);strcpy(p,s);return p;
}
static void input_set_drvdata(struct input_dev *dev,void *data) {(void)dev;(void)data;}
static void meson_ir_input_configure(struct input_dev *dev,void *map) {(void)map;dev->configured=true;}
static int input_register_device(struct input_dev *dev) {
 /* Registration is what exposes IDs/capabilities to udev/libinput. */
 assert(dev->configured && dev->id.bustype==BUS_ISA && dev->id.product);
 return failure==FAIL_REGISTER?-EIO:0;
}
static int strscpy(char *dst,const char *src,size_t size) {snprintf(dst,size,"%s",src);return 0;}
#include "ir_patch_under_test.h"
int main(void) {
 struct meson_ir_dev dev={0};struct meson_ir_chip chip={.r_dev=&dev};
 struct meson_ir_map_tab_list ff={0},dd={0},third={0},replacement={0};
 assert(meson_ir_match_input_dev(&dev,&ff)==NULL);
 assert(meson_ir_setup_map_input(&chip,&ff,NULL)==0 && dev.input_dev_num==1);
 assert(meson_ir_setup_map_input(&chip,&dd,NULL)==0 && dev.input_dev_num==2);
 struct input_dev *first=dev.input_devs[0],*second=dev.input_devs[1];
 assert(meson_ir_match_input_dev(&dev,&ff)==first);
 assert(meson_ir_match_input_dev(&dev,&dd)==second);
 for(int i=0;i<10000;i++) {
  assert(meson_ir_setup_map_input(&chip,&replacement,&dd)==0);
  assert(dev.input_dev_num==2 && dev.input_devs[0]==first && dev.input_devs[1]==second);
  assert(meson_ir_match_input_dev(&dev,&replacement)==second);
 }
 /* IDs from device-tree maps need not be index+1. Preserve them on reload. */
 first->id.product=99;ff.tab.id=first->id;
 assert(meson_ir_setup_map_input(&chip,&replacement,&ff)==0);
 assert(replacement.tab.id.product==99 && dev.input_dev_num==2);
 for(int fail=FAIL_ARRAY;fail<=FAIL_REGISTER;fail++) {
  failure=fail;struct input_dev **before=dev.input_devs;
  assert(meson_ir_setup_map_input(&chip,&third,NULL)<0);
  assert(dev.input_dev_num==2 && dev.input_devs==before);
  assert(meson_ir_match_input_dev(&dev,&ff)==first);
  assert(meson_ir_match_input_dev(&dev,&dd)==second);
 }
 failure=FAIL_NONE;
 assert(meson_ir_setup_map_input(&chip,&third,NULL)==0 && dev.input_dev_num==3);
 assert(meson_ir_match_input_dev(&dev,&third)==dev.input_devs[2]);
 /* A malformed legacy hole must be skipped instead of dereferenced. */
 dev.input_devs[0]=NULL;
 assert(meson_ir_match_input_dev(&dev,&third)==dev.input_devs[2]);
 assert(meson_ir_match_input_dev(&dev,NULL)==NULL);
 free(dev.input_devs);
 for(size_t i=0;i<managed_count;i++){free((void*)managed[i]->name);free(managed[i]);}
 puts("PASS: NEC multiple maps, 10000 reloads, stable IDs, allocation/registration failures and input capabilities");
 return 0;
}
