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
        ca-certificates libboost-program-options1.83.0 libboost-context1.83.0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /src/build/riftbound /app/riftbound
COPY --from=build /src/cards  /app/cards
COPY --from=build /src/decks  /app/decks
COPY --from=build /src/rules  /app/rules
COPY --from=build /src/errata /app/errata
ENV RIFTBOUND_ROOT=/app

EXPOSE 8080
# Non-loopback bind => the server requires an access token and prints the full
# URL (with ?token=...) to stdout; read it with `fly logs`.
# God-mode (shows all hands/decks) is turned off because the port is public.
# stdbuf -oL: stdout is a pipe on Fly, so without it the token URL stays buffered.
CMD ["stdbuf", "-oL", "./riftbound", \
     "--agent1", "human", "--agent2", "mcts:sims=50", \
     "--deck1", "decks/fiora.txt", "--deck2", "decks/yi_rebuild.txt", \
     "--bind", "0.0.0.0", "--port", "8080", "--god-mode", "off"]
