FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:21f6fab17ace4dc76e1c56de91ee95d3d03da021df94b41056ba036f6c6f55e9

COPY .clusterfuzzlite/requirements.txt /tmp/fuzz-requirements.txt
RUN python3 -m pip install --require-hashes -r /tmp/fuzz-requirements.txt
COPY config.py $SRC/deploywhisper/config.py
COPY services $SRC/deploywhisper/services
COPY parsers $SRC/deploywhisper/parsers
COPY evidence $SRC/deploywhisper/evidence
COPY .clusterfuzzlite $SRC/deploywhisper/.clusterfuzzlite
WORKDIR $SRC/deploywhisper
COPY .clusterfuzzlite/build.sh $SRC/build.sh
