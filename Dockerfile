# alpharune (Riftbound simulation engine) web UI, packaged for Fly.io.
# Upstream: https://github.com/chorlick/alpharune  (pinned below)

# ---- build stage -----------------------------------------------------------
FROM ubuntu:24.04 AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git cmake ninja-build g++ \
        libboost-all-dev nlohmann-json3-dev \
    && rm -rf /var/lib/apt/lists/*

ARG ALPHARUNE_REF=ec90f0fed002aed374d06249fa95e83e3cfbd386
RUN git clone https://github.com/chorlick/alpharune.git /src \
    && git -C /src checkout "$ALPHARUNE_REF"
WORKDIR /src
# First configure also fetches OpenSpiel + abseil (needs network).
RUN cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --target riftbound -j"$(nproc)"

# ---- runtime stage ---------------------------------------------------------
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates nginx-light openssl python3 libboost-program-options1.83.0 libboost-context1.83.0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /src/build/riftbound /app/riftbound
COPY --from=build /src/cards  /app/cards
COPY --from=build /src/decks  /app/decks
COPY --from=build /src/rules  /app/rules
COPY --from=build /src/errata /app/errata
ENV RIFTBOUND_ROOT=/app

COPY deploy/entrypoint.sh /app/entrypoint.sh
COPY deploy/launcher.py /app/launcher.py
COPY deploy/nginx.conf.template /app/nginx.conf.template
COPY deploy/rb_proxy.conf /etc/nginx/rb_proxy.conf
COPY deploy/mobile /app/mobile

# riftbound listens on 127.0.0.1:8081 (loopback => no access token); nginx
# listens on 8080 and rewrites Host/Origin. See deploy/entrypoint.sh.
# God-mode (shows all hands/decks) is off because the port is public.
# Set the GAME_PASSWORD secret to require a login (user "player").
EXPOSE 8080
CMD ["/app/entrypoint.sh"]
