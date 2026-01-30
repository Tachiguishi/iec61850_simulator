
PROJECT_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_HOME"

pushd "iec61850"
mkdir -p build && cd build
cmake -DFETCHCONTENT_UPDATES_DISCONNECTED=ON \
	 .. && make -j$(nproc)
popd
