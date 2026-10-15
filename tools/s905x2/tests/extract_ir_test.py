"""Extract the functions under test directly from the shipped native patch."""
import pathlib,sys
patch=pathlib.Path('projects/Amlogic-ce/packages/linux-drivers/amlogic/common_drivers/patches/1002-meson-ir-fix-input-array-on-map-reload.patch').read_text()
def function(source,name):
 start=source.index(name);brace=source.index('{',start);depth=1;end=brace+1
 while depth:
  if source[end]=='{':depth+=1
  if source[end]=='}':depth-=1
  end+=1
 return source[start:end]+'\n'
added=''.join(line[1:]+'\n' for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
core=patch.split('+++ b/drivers/input/ir/meson_ir_core.c\n',1)[1]
reconstructed=''.join(line[1:]+'\n' for line in core.splitlines() if line.startswith((' ','+')))
match=function(reconstructed,'struct input_dev *meson_ir_match_input_dev')
setup=function(added,'static int meson_ir_setup_map_input')
pathlib.Path(sys.argv[1],'ir_patch_under_test.h').write_text(match+setup)
