# gem5-SALAM #

gem5-SALAM (System Architecture for LLVM-based Accelerator Modeling), is a novel system architecture designed to enable LLVM-based modeling and simulation of custom hardware accelerators.

# Requirements

- gem5 dependencies
- LLVM-9 or newer
- Frontend LLVM compiler for preferred development language (eg. clang for C)

# gem5-SALAM Setup

## All Required Dependencies for gem5-SALAM (Ubuntu 20.04)

```bash
sudo apt install build-essential git m4 scons zlib1g zlib1g-dev \
    libprotobuf-dev protobuf-compiler libprotoc-dev libgoogle-perftools-dev \
    python3-dev python-is-python3 libboost-all-dev pkg-config
```

## LLVM/Clang Setup

For a quick start, one can simply run the following to install LLVM and Clang on Ubuntu 20.04.
```bash
sudo apt install llvm-12 llvm-12-tools clang-12
```
After installing these specific libraries, simply run the [update alternatives](https://github.com/TeCSAR-UNCC/gem5-SALAM/blob/main/docs/update-alternatives.sh) script in docs/.

Alternatively, you can install the latest version of LLVM via your system package manager or build from source found at https://github.com/llvm/llvm-project.

# Building gem5-SALAM

Once you have successfully installed all of the necessary dependencies, you can go ahead and clone the gem5-SALAM repository to begin working with it.

```bash
git clone https://github.com/TeCSAR-UNCC/gem5-SALAM
```

When building gem5-SALAM, there are multiple different binary types that can be created. Just like in gem5 the options are debug, opt, fast, prof, and perf. We recommend that users either use the opt or debug builds, as these are the build types we develop and test on.

Below are the bash commands you would use to build the opt or debug binary.

```bash
scons build/ARM/gem5.opt -j`nproc`
```

```bash
scons build/ARM/gem5.debug -j`nproc`
```

For more information regarding the binary types, and other build information refer to the gem5 build documentation [here](http://learning.gem5.org/book/part1/building.html).

# Building with docker

You can use the Dockerfile in the `docker/` directory to build and run gem5-SALAM in a containerized environment with volume mounting (changes sync between host and container).

## Setup

```bash
cd docker

# Configure your user ID (run once)
echo "HOST_UID=$(id -u)" > .env
echo "HOST_GID=$(id -g)" >> .env

# Build the Docker image
docker-compose build
```

## Running

```bash
cd docker
docker-compose run --rm gem5-salam
```

This will start a container with the repository mounted at `/gem5-SALAM`. Any changes made inside the container will be reflected on your host machine, and vice versa.

## Building gem5-SALAM inside the container

Once inside the container, build gem5-SALAM:

```bash
scons build/ARM/gem5.opt -j$(nproc)
```

## Running benchmarks inside the container

```bash
cd $M5_PATH/benchmarks/sys_validation/bfs
make
$M5_PATH/tools/run_system.sh --bench bfs --bench-path benchmarks/sys_validation/bfs
```

# Using gem5-SALAM

To use gem5-SALAM you need to define the computation model of you accelerator in your language of choice,and compile it to LLVM IR. Any control and dataflow graph optimization (eg. loop unrolling) should be handled by the compiler. You can construct accelerators by associating their LLVM IR with an LLVMInterface and connecting it to the desired CommInterface in the gem5 memory map.

Below are some resources in the gem5-SALAM directory that can be used when getting started:

- Examples for system-level configuration can be found in **configs/common/HWAcc.py**.
- Accelerator benchmarks and examples can be found in the **benchmarks** directory.
- The **benchmarks/common** directory contains basic drivers and syscalls for baremetal simulation.
- **benchmarks/sys_validation** contains examples for configuring and using gem5-SALAM with different algorithms.

## System Validation Examples

The system validation examples under **benchmarks/sys_validation** are good examples for how you interface with the gem5-SALAM simulation objects.

## Running MobileNetV2 Benchmark

MobileNetV2 is a neural network benchmark that demonstrates gem5-SALAM's accelerator capabilities.

```bash
cd $M5_PATH/benchmarks/mobilenetv2
make
```

**Run with tracing:**
```bash
./tools/run_system.sh --bench mobilenetv2 --bench-path benchmarks/mobilenetv2 --config-name 1_config.yml -f "LLVMInterface,NoncoherentDma,CommInterface" -p
```

**View results:**
```bash
cat BM_ARM_OUT/benchmarks/mobilenetv2/debug-trace.txt
```

In order to use the system validation benchmarks, it is required to have the ARM GCC cross-compiler installed. If you didn't already install it when you setup the dependencies, you can install it in Ubuntu by running the below command:

```bash
sudo apt-get install gcc-multilib gcc-arm-none-eabi
```

**run_system.sh** requires an environment variable named **M5_PATH** to be set. You will want to point it to your gem5-SALAM path as shown below.

```bash
export M5_PATH=/path/to/gem5-SALAM
```

Next, compile your desired example.

```bash
cd $M5_PATH/benchmarks/sys_validation/[benchmark]
make
```

Finally, you can run any of the benchmarks you have compiled by running the run system script.

```bash
$M5_PATH/tools/run_system.sh --bench bfs --bench-path benchmarks/sys_validation/bfs
```

If you would like to see the gem5-SALAM command created by the shell file you would just need to inspect the **RUN_SCRIPT** variable in the shell file.

# Resources

## gem5 Documentation

https://www.gem5.org/documentation/

## gem5 Tutorial

The gem5 documentation has a [tutorial for working with gem5](http://learning.gem5.org/book/index.html#) that will help get you started with the basics of creating your own sim objects.

## Building and Integrating Accelerators in gem5-SALAM

We have written a guide on how to create the GEMM system validation example. This will help you get started with creating your own benchmarks and systems. It can be viewed [here](https://github.com/TeCSAR-UNCC/gem5-SALAM/blob/master/docs/Building_and_Integrating_Accelerators.md).

## SALAM Object Overview

The [SALAM Object Overview](https://github.com/TeCSAR-UNCC/gem5-SALAM/blob/master/docs/SALAM_Object_Overview.md) covers what various Sim Objects in gem5-SALAM are and their purpose.

## Full-system OS Simulation ##

Please download the latest version of the Linux Kernel for ARM from the [gem5 ARM kernel page](http://gem5.org/ARM_Kernel).
You will also need the [ARM disk images](http://www.gem5.org/dist/current/arm/) for full system simulation.
Devices operate in the physical memory address space.
