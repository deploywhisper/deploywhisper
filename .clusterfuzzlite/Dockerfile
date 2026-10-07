FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:f606cee856c34585c314af4fbc41940bce398f5244fbfc757116188828f473c6

COPY .clusterfuzzlite/requirements.txt /tmp/fuzz-requirements.txt
RUN python3 -m pip install --require-hashes -r /tmp/fuzz-requirements.txt
COPY config.py $SRC/deploywhisper/config.py
COPY services $SRC/deploywhisper/services
COPY parsers $SRC/deploywhisper/parsers
COPY evidence $SRC/deploywhisper/evidence
COPY .clusterfuzzlite $SRC/deploywhisper/.clusterfuzzlite
WORKDIR $SRC/deploywhisper
COPY .clusterfuzzlite/build.sh $SRC/build.sh
