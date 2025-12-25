# Sample invocation:
#    docker build . --file docker/Dockerfile --build-arg BUILD_TYPE="opt"

FROM ubuntu:20.04

SHELL ["/bin/bash", "-c"]

ARG BUILD_TYPE

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

WORKDIR /gem5-SALAM
COPY . /gem5-SALAM
ENV M5_PATH=/gem5-SALAM
RUN docs/update-alternatives.sh

# Build gem5-SALAM.
RUN scons build/ARM/gem5."$BUILD_TYPE" -j`nproc`

# Build a benchmark.
WORKDIR  $M5_PATH/benchmarks/sys_validation/bfs
RUN make

# Run a benchmark.
WORKDIR /gem5-SALAM
# RUN ./systemValidation.sh -b bfs
