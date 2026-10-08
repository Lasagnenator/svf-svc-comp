# pysvf's bundled LLVM and SVF binaries link libxml2.so.2, which Ubuntu 26.04 replaced
# with the ABI-incompatible libxml2.so.16. Take the old library and its ICU from 24.04.
FROM ubuntu:24.04 AS libxml2-compat
RUN apt-get update && apt-get install -y --no-install-recommends libxml2 \
    && mkdir /compat \
    && cp -L /usr/lib/x86_64-linux-gnu/libxml2.so.2 \
             /usr/lib/x86_64-linux-gnu/libicuuc.so.74 \
             /usr/lib/x86_64-linux-gnu/libicudata.so.74 /compat/

FROM ubuntu:26.04

# Stop ubuntu-20 interactive options.
ENV DEBIAN_FRONTEND=noninteractive

# Install SSH server
RUN apt-get update && apt-get install -y openssh-server
RUN mkdir -p /var/run/sshd

# Define home
ENV HOME=/home/svf
ENV APP_DIR=${HOME}/svf-svc-comp
RUN useradd --create-home --uid 10001 --shell /bin/bash svf

# Make .ssh directory in root, no one else but root has full access
RUN mkdir -p /home/svf/.ssh && chmod 700 /home/svf/.ssh

# Copy team public key file into svf's authorised keys
COPY authorized_keys /home/svf/.ssh/authorized_keys

# No one else svf account has read and write access to authorized keys
RUN chmod 600 /home/svf/.ssh/authorized_keys

RUN chown -R svf:svf /home/svf/.ssh

# Login in as svf
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config

# Disable password authentication
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

# Container will listen on port 22
EXPOSE 22

# Run SSH when container starts
CMD ["/usr/sbin/sshd", "-D"]


# Define dependencies.
ENV lib_deps="cmake g++ gcc clang-21 llvm-21 git zlib1g-dev libncurses-dev libtinfo6 build-essential libssl-dev libpcre2-dev zip libzstd-dev"
ENV build_deps="wget xz-utils git gdb tcl software-properties-common"

# Fetch dependencies.
RUN apt-get update --fix-missing
RUN apt-get install -y --no-install-recommends $build_deps $lib_deps

# pysvf only ships wheels up to CPython 3.12, but Ubuntu 26.04 only has 3.14,
# so uv provides a standalone 3.12. Keep it outside /root so the svf user can run it.
RUN apt-get update && apt-get install -y python3
COPY --from=libxml2-compat /compat/ /opt/compat-libs/
RUN echo /opt/compat-libs > /etc/ld.so.conf.d/pysvf-compat.conf && ldconfig
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python UV_LINK_MODE=copy UV_NO_CACHE=1
COPY requirements.txt /tmp/requirements.txt
RUN uv venv --python 3.12 /opt/venv
RUN uv pip install --python /opt/venv/bin/python -r /tmp/requirements.txt
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
RUN echo 'export PATH="/opt/venv/bin:$PATH"' >> /etc/profile


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
RUN python -c "import pysvf, yaml"
USER root
