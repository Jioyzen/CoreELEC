# SPDX-License-Identifier: GPL-2.0-only
# Source from the repository root before package builds or image builds.
if [ -f "${XDG_CONFIG_HOME:-${HOME}/.config}/coreelec-jiefu/build.env" ]; then
  . "${XDG_CONFIG_HOME:-${HOME}/.config}/coreelec-jiefu/build.env"
fi
export PROJECT=Amlogic-ce DEVICE=Amlogic-no ARCH=aarch64 DISTRO=CoreELEC
export JIEFU_BOARD=yes S905X2_BOARD=no JIOYZEN_MEDIA_EDITION=yes
export BUILD_SUFFIX=jiefu
export BUILD_DIR=${BUILD_DIR:-${PWD}/.work/jiefu}
export TARGET_DIR=${TARGET_DIR:-${PWD}/target/jiefu}
export JIOYZEN_MEDIA_PAYLOAD_DIR=${BUILD_DIR}/media-payload-jiefu
export THREADCOUNT=${THREADCOUNT:-2}
export CONCURRENCY_MAKE_LEVEL=${CONCURRENCY_MAKE_LEVEL:-3}
export CONCURRENCY_LOAD=${CONCURRENCY_LOAD:-4}
export BUILDER_NAME=Jioyzen BUILDER_VERSION=jiefu-s905x2-no
