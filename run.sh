
export LD_LIBRARY_PATH=./lib:$LD_LIBRARY_PATH
# python -c "import pyiec61850"
python main.py "$@"
