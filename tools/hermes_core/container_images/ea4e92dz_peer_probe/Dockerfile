# Inert peer-observation helper only. No receiver or provider command.
FROM registry.librechat.ai/danny-avila/librechat-dev@sha256:3144a862c5947599f5eeab3f9dfde33a690fa98d01065b9d66576da43a692561
USER node
WORKDIR /opt/ea4e-peer
COPY --chown=node:node marker.js /opt/ea4e-peer/marker.js
ENTRYPOINT ["node", "/opt/ea4e-peer/marker.js"]
