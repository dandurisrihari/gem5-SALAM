# Sample invocation (with volume mount for bidirectional sync):
#    docker build . --file docker/Dockerfile --build-arg HOST_UID=$(id -u) --build-arg HOST_GID=$(id -g) -t gem5-salam
#    docker run -it -v $(pwd):/gem5-SALAM gem5-salam
#
# To build gem5 inside container after mounting:
#    scons build/ARM/gem5.opt -j$(nproc)

FROM ubuntu:20.04

SHELL ["/bin/bash", "-c"]

# Build arguments for user creation
ARG HOST_UID=1000
ARG HOST_GID=1000
ARG USERNAME=developer

# Install required packages.
RUN export DEBIAN_FRONTEND=noninteractive && export TZ=America/New_York && \
    apt-get update && \
    apt-get install -yqq \
        apt-utils sudo \
        build-essential cmake git \
        libssl-dev pkg-config python3 python3-pip \
        zlib1g zlib1g-dev m4 \
        scons libprotobuf-dev protobuf-compiler \
        libprotoc-dev libgoogle-perftools-dev \
        gcc-multilib g++-multilib \
        python3-dev python-is-python3 python3-yaml \
        libboost-all-dev gcc-arm-none-eabi \
        llvm-9 clang-9 \
        wget lsb-release software-properties-common gnupg \
        libpng-dev

# Install LLVM-12 using official script
RUN wget https://apt.llvm.org/llvm.sh && \
    chmod +x llvm.sh && \
    ./llvm.sh 12 all && \
    rm llvm.sh

# Create user with same UID/GID as host user
RUN groupadd --gid ${HOST_GID} ${USERNAME} && \
    useradd --uid ${HOST_UID} --gid ${HOST_GID} -m ${USERNAME} && \
    echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Set up working directory and environment
WORKDIR /gem5-SALAM
ENV M5_PATH=/gem5-SALAM
ENV HOME=/home/${USERNAME}

# Copy only the update-alternatives script and run it
COPY docs/update-alternatives.sh /tmp/update-alternatives.sh
RUN chmod +x /tmp/update-alternatives.sh && /tmp/update-alternatives.sh

# Switch to non-root user
USER ${USERNAME}

# Set default command
CMD ["/bin/bash"]
