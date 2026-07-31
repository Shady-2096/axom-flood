FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/axom-cloudrun

COPY probe.py run-job.sh ./
RUN chmod 0755 run-job.sh

ENTRYPOINT ["/opt/axom-cloudrun/run-job.sh"]
CMD ["probe"]
