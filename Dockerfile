FROM ubuntu:24.04

# Stop ubuntu-20 interactive options.
ENV DEBIAN_FRONTEND noninteractive

# Define home
ENV HOME=/home/svf
ENV APP_DIR=${HOME}/svf-svc-comp
RUN useradd --create-home --uid 10001 --shell /bin/bash svf

# Define dependencies.
ENV lib_deps="cmake g++ gcc git zlib1g-dev libncurses5-dev libtinfo6 build-essential libssl-dev libpcre2-dev zip libzstd-dev"
ENV build_deps="wget xz-utils git gdb tcl software-properties-common"

# Fetch dependencies.
RUN apt-get update --fix-missing
RUN apt-get install -y --no-install-recommends $build_deps $lib_deps

# Install Python and set up venv
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    libxml2
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv
RUN /opt/venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Fix SABER's missing import
ENV PYSVF_ROOT=/opt/venv/lib/python3.12/site-packages/pysvf/SVF
RUN ln -sfn \
    "${PYSVF_ROOT}/llvm-21.1.0.obj/lib/libLLVM.so" \
    "${PYSVF_ROOT}/Release-build/lib/libLLVM.so.21.1"

# Fetch and build this repository
WORKDIR ${APP_DIR}
COPY --chown=svf:svf . .
# No build step required currently.

# Build-time check to see that things probably are working
USER svf
RUN python -c "import pysvf, yaml, z3"
