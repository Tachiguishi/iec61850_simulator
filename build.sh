
PROJECT_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_HOME"
mkdir -p lib

PYTHON_SITE_PACKAGES_DIR=$(python -c "import site; print(site.getsitepackages()[0])")

pushd "src/libiec61850"

# build third_party/mbedtls
# dnf install -y mbedtls-devel
# apt install -y libmbedtls-dev
# pushd third_party/mbedtls
# # checke if mbedtls v3.6.0 is already downloaded
# if [ ! -d "mbedtls-3.6.0" ]; then
# 	wget https://github.com/Mbed-TLS/mbedtls/archive/refs/tags/v3.6.0.tar.gz && tar xzf v3.6.0.tar.gz
# fi
# popd
#  -DCONFIG_EXTERNAL_MBEDTLS_INCLUDE_PATH=/usr/include \
#  -DCONFIG_EXTERNAL_MBEDTLS_DYNLIB_PATH=/usr/lib64 \

mkdir -p build && cd build
cmake -DBUILD_EXAMPLES=OFF \
	 -DFETCHCONTENT_UPDATES_DISCONNECTED=ON \
	 -DBUILD_PYTHON_BINDINGS=ON \
	 -DCONFIG_USE_EXTERNAL_MBEDTLS_DYNLIB=OFF \
	 .. && make
cp -P src/libiec61850.so* "$PROJECT_HOME/lib/"
cp pyiec61850/*pyiec61850.* "$PYTHON_SITE_PACKAGES_DIR/"
popd
