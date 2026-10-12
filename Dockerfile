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
ENV lib_deps="clang-21 git zlib1g-dev libncurses-dev libtinfo6 build-essential libssl-dev libpcre2-dev zip libzstd-dev"
ENV build_deps="wget xz-utils git gdb tcl software-properties-common"
ENV runtime="python3 python3-venv"

# Fetch dependencies.
RUN apt-get update --fix-missing
RUN apt-get install -y --no-install-recommends $build_deps $lib_deps $runtime

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
RUN echo 'export PATH="/opt/venv/bin:$PATH"' >> /etc/profile
RUN pip install -r /tmp/requirements.txt


# Fix SABER's missing import
#ENV PYSVF_ROOT=/opt/venv/lib/python3.14/site-packages/pysvf/SVF
#RUN ln -sfn \
#    "${PYSVF_ROOT}/llvm-21.1.0.obj/lib/libLLVM.so" \
#    "${PYSVF_ROOT}/Release-build/lib/libLLVM.so.21.1"

# Fetch and build this repository
RUN mkdir -p ${APP_DIR}
RUN chown svf:svf ${APP_DIR}
WORKDIR ${APP_DIR}
COPY --chown=svf:svf . .
# No build step required currently.

# Build-time check to see that things probably are working
USER svf
RUN python -c "import pysvf, yaml"
USER root
