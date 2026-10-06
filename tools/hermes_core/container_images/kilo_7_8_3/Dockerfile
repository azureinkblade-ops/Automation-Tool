# Provisional packaging only. Building this image does not qualify execution.
FROM debian:bookworm-slim@sha256:a4672c0cb26fbdde88e38fa2dfb6c681942306680e41e4378b28770b6e79ee91 AS unpack

COPY kilo-linux-x64.tar.gz /tmp/kilo-linux-x64.tar.gz
RUN echo '43c32cc25e09f2c8ae82faf480f482fb7de1f34ec5047edfde86158681ccb6bc  /tmp/kilo-linux-x64.tar.gz' | sha256sum -c - \
    && mkdir -p /opt/kilo \
    && tar -xzf /tmp/kilo-linux-x64.tar.gz -C /opt/kilo

FROM debian:bookworm-slim@sha256:a4672c0cb26fbdde88e38fa2dfb6c681942306680e41e4378b28770b6e79ee91
COPY --from=unpack /opt/kilo/ /opt/kilo/
RUN mkdir -p /tmp/kilo-home /work \
    && chown 65532:65532 /tmp/kilo-home /work
ENV HOME=/tmp/kilo-home
WORKDIR /work
USER 65532:65532
ENTRYPOINT ["/opt/kilo/kilo"]
