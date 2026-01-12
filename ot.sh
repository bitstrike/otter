# TODO: should probably not validate the ignore line as Guake isn't visible unless active?
#strace -o /tmp/otter.debug ./otter.py --main-character --recent --north --xsize 150 --nrows 1 --notitle --ignore Guake\! --verbose
#strace -o /tmp/otter.debug ./otter.py --main-character --recent --north --xsize 150 --nrows 1 --notitle --verbose
strace -o /tmp/otter2.debug ./otter2.py --main-character --recent --north --xsize 150 --nrows 1 --notitle --verbose
