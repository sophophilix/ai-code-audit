# The kit's sandbox image (ADR 0005). Built by `kit sandbox`, never by an agent.
# The Node.js major comes from the target's engines or .nvmrc. The kit records the
# built image's id in .audit/scans/dynamic/jobs.log, so every job names exactly
# what it ran in.
ARG NODE_MAJOR=26
FROM node:${NODE_MAJOR}-bookworm-slim

# Analysis tools at pinned versions, each at least two weeks old when pinned
# (knip: ISC, dependency-cruiser: MIT). Installed with scripts off, outside /work.
RUN npm install --global --ignore-scripts --no-audit --no-fund \
      knip@6.42.1 dependency-cruiser@18.7.0 \
 && npm cache clean --force

# The node image's unprivileged user. /work is the copy of the target; /tmp is
# the only writable place once the network is off.
USER node
WORKDIR /work
ENV HOME=/tmp NPM_CONFIG_IGNORE_SCRIPTS=true NPM_CONFIG_UPDATE_NOTIFIER=false
