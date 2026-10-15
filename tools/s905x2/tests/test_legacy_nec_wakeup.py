"""Exercise the actual legacy NEC helper with a fake mailbox provider."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
PATCH = ROOT / 'projects/Amlogic-ce/packages/linux-drivers/amlogic/common_drivers/patches/1004-s905x2-oem-bl30-nec-wakeup.patch'

STUBS = r'''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
typedef uint32_t u32;
struct device { int unused; };
struct platform_device { struct device dev; };
struct mbox_client { struct device *dev; bool tx_block; unsigned tx_tout; };
struct mbox_chan { int unused; };
struct aml_mbox_data {
 int cmd, client_id; void *txbuf; u32 txsize; void *rxbuf; u32 rxsize; int sync;
};
static struct platform_device pdev;
static struct platform_device *bl30_pdev = &pdev;
static struct mbox_chan chan;
static u32 remotewakeup, decode_type;
static int legacy_nec_lock;
static bool legacy_nec_attempted;
static int legacy_nec_result;
static int requests, sends, frees, provider_error, transport_result;
static u32 firmware_status, sent_code;
#define MBOX_CMD_SET_USR_DATA 0x20
#define AML_MBOX_CL_REMOTE 5
#define MBOX_SYNC 1
#define DRIVER_NAME "test"
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)
static void mutex_lock(int *lock) { assert(!*lock); *lock = 1; }
static void mutex_unlock(int *lock) { assert(*lock); *lock = 0; }
static struct mbox_chan *mbox_request_channel_byname(struct mbox_client *c, const char *name)
{
 requests++; assert(c->dev == &pdev.dev && c->tx_block && c->tx_tout == 2000);
 assert(!strcmp(name, "ree2aocpu"));
 return provider_error ? (struct mbox_chan *)(intptr_t)provider_error : &chan;
}
static void mbox_free_channel(struct mbox_chan *c) { assert(c == &chan); frees++; }
static int aml_mbox_transfer(struct mbox_chan *c, struct aml_mbox_data *d, int sync)
{
 sends++; assert(c == &chan);
 assert(d->cmd == 0x20 && d->client_id == 5);
 assert(d->txsize == 4 && d->rxsize == 4 && d->sync == 1 && sync == 1);
 sent_code = *(u32 *)d->txbuf;
 *(u32 *)d->rxbuf = firmware_status;
 return transport_result;
}
'''

CASES = r'''
static void reset(u32 code)
{
 remotewakeup = code; decode_type = 0;
 legacy_nec_attempted = false; legacy_nec_result = 0;
 requests = sends = frees = provider_error = transport_result = 0;
 firmware_status = sent_code = 0;
 assert(!legacy_nec_lock);
}
int main(void)
{
 /* Match the observed OEM comparator: full NEC frame loses its inverse byte. */
 reset(0x23dcdd22); assert(!setup_legacy_nec_wakeup());
 assert(sent_code == 0x00dcdd22 && sends == 1 && frees == 1);
 assert(!setup_legacy_nec_wakeup() && sends == 1 && requests == 1);
 reset(0x00dcdd22); transport_result = 3;
 assert(!setup_legacy_nec_wakeup() && sent_code == 0x00dcdd22);
 reset(0); assert(!setup_legacy_nec_wakeup() && requests == 0 && sends == 0);
 reset(0x00dcdd22); decode_type = 1;
 assert(setup_legacy_nec_wakeup() == -EOPNOTSUPP && !requests);
 reset(0x00dcdd22); provider_error = -EBUSY;
 assert(setup_legacy_nec_wakeup() == -EBUSY && !sends && !frees);
 provider_error = 0;
 assert(!setup_legacy_nec_wakeup() && requests == 2 && sends == 1);
 reset(0x00dcdd22); firmware_status = 10;
 assert(setup_legacy_nec_wakeup() == -EREMOTEIO && frees == 1);
 assert(setup_legacy_nec_wakeup() == -EREMOTEIO && sends == 1);
 reset(0x00dcdd22); transport_result = -ETIME;
 assert(setup_legacy_nec_wakeup() == -ETIME && frees == 1);
 assert(setup_legacy_nec_wakeup() == -ETIME && sends == 1);
 assert(!legacy_nec_lock);
 puts("legacy NEC payload, once-only, disable, protocol, provider retry, firmware rejection and timeout checks passed");
}
'''

class LegacyNecWakeupTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'), 'host C compiler required')
    def test_actual_helper_with_mailbox_provider(self):
        # Reconstruct new hunk contents, exercising production C rather than
        # a Python reimplementation of its protocol or state machine.
        driver = PATCH.read_text().split('+++ b/drivers/bootloader/bl30_manager.c\n', 1)[1].split('--- a/', 1)[0]
        new = '\n'.join(line[1:] for line in driver.splitlines()
                        if line.startswith(('+', ' ')))
        helper = 'static int setup_legacy_nec_wakeup' + new.split('static int setup_legacy_nec_wakeup', 1)[1].split('static ssize_t setup_bl30_store', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / 'test.c'
            binary = pathlib.Path(tmp) / 'test'
            source.write_text(STUBS + helper + CASES)
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)], check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

if __name__ == '__main__':
    unittest.main()
