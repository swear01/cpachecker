# Self-contained reproduction image for the VGuide artifact.
#
#   docker build -t vguide-artifact -f Dockerfile .
#   docker run --rm vguide-artifact                       # offline + build-free reproduction
#   docker run --rm -e DEEPSEEK_API_KEY=sk-... vguide-artifact full   # + live VGuide LLM arm
#
# The bundle ships prebuilt classes/ and all runtime jars (lib/), so the default run needs
# NO build and NO network. python3 + a JRE are the only requirements; ant is included only
# for an optional rebuild from source.
FROM eclipse-temurin:21-jdk

RUN apt-get update \
 && apt-get install -y --no-install-recommends ant python3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /vguide
COPY cpachecker /vguide/cpachecker
COPY sv-benchmarks /vguide/sv-benchmarks
ENV SV_BENCHMARKS=/vguide/sv-benchmarks/c

# Default: run the reproduction (offline Table 3 + unit tests + a real stock-baseline smoke).
# Pass "full" plus -e DEEPSEEK_API_KEY=... to also re-run the live VGuide arm.
ENTRYPOINT ["bash", "/vguide/cpachecker/artifact/reproduce.sh"]
CMD []
