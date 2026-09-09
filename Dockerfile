FROM ubuntu:24.04

# Stop ubuntu-20 interactive options.
ENV DEBIAN_FRONTEND=noninteractive

# Install SSH server
RUN apt-get update && apt-get install -y openssh-server
RUN mkdir /var/run/sshd

# Make .ssh directory in root, no one else but root has full access
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# Copy team public key file into root's authorised keys
COPY authorized_keys /root/.ssh/authorized_keys

# No one else but root has read and write access to authorized keys
RUN chmod 600 /root/.ssh/authorized_keys

# Allow root login with key only
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config

# Disable password authentication
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

# Container will listen on port 22
EXPOSE 22

# Run SSH when container starts
CMD ["/usr/sbin/sshd", "-D"]

# Define home
ENV HOME=/home/svf
ENV APP_DIR=${HOME}/svf-svc-comp
RUN useradd --create-home --uid 10001 --shell /bin/bash svf

# Define dependencies.
ENV lib_deps="cmake g++ gcc clang git zlib1g-dev libncurses5-dev libtinfo6 build-essential libssl-dev libpcre2-dev zip libzstd-dev"
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
# Install pyyaml because it's likely needed for testing
RUN /opt/venv/bin/python -m pip install pyyaml
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
RUN python -c "import pysvf, yaml"
USER root