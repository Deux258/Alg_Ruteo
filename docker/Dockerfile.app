FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS dependencies
ARG BUILD_COMMIT=unknown
ENV BUILD_COMMIT=$BUILD_COMMIT
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY docker/packages/libexpat1_2.5.0-1+deb12u5_amd64.deb /tmp/libexpat1.deb
RUN echo 'cae5ded666d8573dd33060bc66fbac21eea8b101a6b56e2af8bd590fcfa65d79  /tmp/libexpat1.deb' | sha256sum -c - \
    && dpkg -i /tmp/libexpat1.deb && rm /tmp/libexpat1.deb
COPY requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock
COPY requirements.aerial.lock /app/requirements.aerial.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.aerial.lock
COPY requirements.patrol.lock /app/requirements.patrol.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.patrol.lock
RUN python -m pip check

# QA tools exist only in the explicit test target.
FROM dependencies AS test
COPY --from=node:24.21.0-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 /usr/local/bin/node /usr/local/bin/node
COPY requirements.test.lock /app/requirements.test.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.test.lock \
    && python -m playwright install --with-deps chromium
COPY . /app
CMD ["python", "-m", "tools.ci_acceptance"]

FROM dependencies AS app
COPY . /app
CMD ["python", "-m", "core.pipeline", "run"]
