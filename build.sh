
PWD=$(pwd)
pushd deps/libiec61850
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=./install -DBUILD_PYTHON_BINDINGS=ON .. && make && make install
popd
