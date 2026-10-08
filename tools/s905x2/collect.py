#!/usr/bin/env python3
"""Validate compiled board artifacts and collect a flash image and update tar."""
import hashlib,json,os,pathlib,shutil,subprocess,tarfile,datetime
root=pathlib.Path(__file__).resolve().parents[2]
target=pathlib.Path(os.environ.get('TARGET_DIR',root/'target'))
build=pathlib.Path(os.environ.get('BUILD_DIR',root))/'build.CoreELEC-Amlogic-no.aarch64-22'
system=build/'image/system'
out=target/'s905x2-release'
if out.exists():
 assert out.parent==target and out.name=='s905x2-release'
 shutil.rmtree(out)
out.mkdir()
manifest=json.loads((root/'projects/Amlogic-ce/packages/s905x2-board/sources/manifest.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
run=lambda *a:subprocess.check_output(a,text=True).strip()
module=list(system.glob('usr/lib/kernel-overlays/**/88x2cs.ko'))
if not module:module=list(system.rglob('88x2cs.ko'))
assert len(module)==1, 'RTL8822CS vendor module missing/ambiguous'
assert sha(system/'usr/lib/coreelec/dovi.ko')==manifest['dovi_sha256']
dtb=system/'usr/share/bootloader/device_trees/g12a_s905x2_u212_2g_rtl8822cs.dtb'
assert dtb.exists(), 'custom DTB missing'
assert run('fdtget','-t','u',str(dtb),'/vpu','clk_level')=='8'
assert run('fdtget','-t','x',str(dtb),'/reserved-memory/linux,meson-fb','reg')=='0 7f800000 0 800000'
assert run('fdtget',str(dtb),'/','amlogic-dt-id')==manifest['dt_id']
assert run('fdtget',str(dtb),'/','coreelec-dt-id')==manifest['dt_id'], 'upgrade selector differs from custom board'
assert 'sd-uhs-sdr104' in run('fdtget','-p',str(dtb),'/sd2@ffe05000')
kodi=system/'usr/lib/kodi/kodi.bin'
assert b'amcodec_dv: collect cold dual-layer input' in kodi.read_bytes(), 'native Kodi DV guard missing'
assert b'amcodec_dv: restore EL parameters' in kodi.read_bytes(), 'native Kodi seek headers missing'
hevc=list(system.rglob('amvdec_h265.ko'))
assert len(hevc)==1 and b'dv_el_start_policy' in hevc[0].read_bytes(), 'native HEVC DV patch missing'
# Select this build's image/tar by shared stem, excluding previous release copies.
images=sorted(target.glob('*Amlogic-no.aarch64*Generic.img.gz'),key=lambda p:p.stat().st_mtime)
assert images,'image missing'
image=images[-1];stem=image.name.removesuffix('-Generic.img.gz')
update=target/(stem+'.tar');assert update.exists(),'matching update package missing'
with tarfile.open(update) as t:
 names=t.getnames()
 assert any(n.endswith('/target/KERNEL') for n in names)
 assert any(n.endswith('/target/SYSTEM') for n in names)
 assert any(n.endswith('/device_trees/'+dtb.name) for n in names),'update DTB missing'
revision=run('git','-C',str(root),'rev-parse','HEAD')
now=datetime.datetime.now(datetime.timezone.utc)
manifest.update(source_commit=revision,built_utc=now.isoformat(),release_tag=now.strftime('%Y%m%d-%H%M')+'-s905x2-'+revision[:8])
for p,n in [(image,stem+'-S905X2-U212-2G-RTL8822CS.img.gz'),(update,stem+'-S905X2-U212-2G-RTL8822CS.tar')]:shutil.copy2(p,out/n)
# Verify the boot partition really contains the selected DTB and dovi file.
import gzip,tempfile,struct
with tempfile.TemporaryDirectory(prefix='ce-image-check-') as tmp:
 raw=pathlib.Path(tmp)/'image.img'
 with gzip.open(image,'rb') as src,raw.open('wb') as dst:shutil.copyfileobj(src,dst)
 with raw.open('rb') as f:
  sector=f.read(512);start=struct.unpack_from('<I',sector,446+8)[0]*512
 for name,expected in [('dtb.img',dtb),('dovi.ko',system/'usr/lib/coreelec/dovi.ko')]:
  dest=pathlib.Path(tmp)/name
  subprocess.run(['mcopy','-i',str(raw)+'@@'+str(start),'::/'+name,str(dest)],check=True)
  assert sha(dest)==sha(expected),name+' boot partition mismatch'
for label,path in [('linux','projects/Amlogic-ce/packages/linux/package.mk'),('common_drivers','projects/Amlogic-ce/packages/linux-drivers/amlogic/common_drivers/package.mk'),('media_modules','projects/Amlogic-ce/packages/linux-drivers/amlogic/media_modules-aml/package.mk'),('kodi','projects/Amlogic-ce/packages/mediacenter/kodi/package.mk')]:
 import re
 manifest[label+'_commit']=re.search(r'^PKG_VERSION="([^"]+)"', (root/path).read_text(),re.M)[1]
manifest['artifacts']={p.name:sha(p) for p in out.iterdir() if p.suffix in ['.gz','.tar']}
(out/'build-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(out/'RELEASE-NOTES.md').write_text('S905X2 / u212-compatible / 2GB DDR3 / RTL8822CS 专用镜像。\n\n默认修复 DTB，内置已验证 dovi.ko；包含 HDMI、Wi-Fi、DV seek 与续播修复。下载 .img.gz 刷写；.tar 用于本分支升级。CEC 保持官方默认逻辑。\n\n源码 commit：'+revision+'\n\n每周自动产物仅经过构建和结构检查；实机验证记录见仓库。\n')
(out/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(out.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
print(out)
