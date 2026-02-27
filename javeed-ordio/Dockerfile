FROM python:3.13-slim

WORKDIR /build

COPY pyproject.toml README.md ./
COPY javeed_ordio/ javeed_ordio/
COPY config/ config/
COPY allocation_core/ allocation_core/

RUN pip install --no-cache-dir .

ENV HOST=0.0.0.0
ENV ORDIO_LITE_ARTIFACT_DIR=/tmp/artifacts

EXPOSE 8080

CMD ["javeed-ordio-mcp", "--transport", "streamable-http"]
