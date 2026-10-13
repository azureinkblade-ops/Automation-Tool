# Source-only fake gateway recipe. Building or starting an image requires a separate gate.
FROM registry.librechat.ai/danny-avila/librechat-dev@sha256:3144a862c5947599f5eeab3f9dfde33a690fa98d01065b9d66576da43a692561
USER node
WORKDIR /opt/ea4e-ping-gateway
COPY --chown=node:node gateway.js /opt/ea4e-ping-gateway/gateway.js
ENTRYPOINT ["node", "/opt/ea4e-ping-gateway/gateway.js"]
