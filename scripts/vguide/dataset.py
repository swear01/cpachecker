#!/usr/bin/env python3

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
import bz2
import collections
import csv
import datetime
import hashlib
import importlib.util
import json
import os
import re
import signal
import shutil
import stat
import statistics
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("baseline", Path(__file__).with_name("baseline.py"))
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)

LOOP = re.compile(r"\b(?:while|for)\s*\(|\bdo\s*\{")
ERROR_CALL = re.compile(r"\b(?:reach_error|__VERIFIER_error)\s*\(")
SOURCE_REFERENCE = re.compile(r"(?<![-\w./])([\w./+-]+\.c)(?![\w./])")
SOURCE_LICENSES = {
    "cbmc": "BSD-4-Clause",
    "esbmc": "Apache-2.0 AND BSD-4-Clause",
    "seahorn": "BSD-3-Clause-CMU",
}
SOURCE_LICENSE_FILES = {
    "cbmc": "LICENSE",
    "esbmc": "COPYING",
    "seahorn": "license.txt",
}
SOURCE_URLS = {
    "cbmc": "https://github.com/diffblue/cbmc",
    "esbmc": "https://github.com/esbmc/esbmc",
    "seahorn": "https://github.com/seahorn/seahorn",
    "sv-benchmarks": "https://gitlab.com/sosy-lab/benchmarking/sv-benchmarks",
}
ANALYSIS_UNSOLVED = {"timeout", "out_of_memory", "unknown"}
DISCOVERY_HOSTS = ("athena", "cthulhu", "valkyrie")
REROUTE_HOSTS = ("athena", "valkyrie")
FROZEN_CTHULHU_MANIFEST_SHA256 = (
    "40bda9c755c88d9b617269aaa6e1c66ceea07fb818e0741f8a1f960536bd6d4b"
)
FROZEN_ATHENA_MANIFEST_SHA256 = (
    "5b0224af541b371fd8f882cf71099b774fdd33dc3187cf6dca31cc3c8ca55cef"
)
FROZEN_ATHENA_REROUTE_MANIFEST_SHA256 = (
    "477374a2bbab9fd8559e1945e6781b5484e26afec7808266332423c1db9cddd6"
)
FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256 = (
    "59681ac7dbbf177ae6a4ce3cfd3bd5e5b45d57658c1d6ed467c74e1cd4f60f04"
)
FROZEN_PARENT_MANIFEST_SHA256 = (
    "6b5b997c424c8649d9492a84caae1b486b6936e2e843a1d43a22944cae39ac3c"
)
FROZEN_PHASE_A_MANIFEST_SHA256 = {
    "original_valkyrie": (
        "64f25378a401f1936fc836b5901c96d304f9c654f5c9d4cf17327e086463930d"
    ),
    "reroute_valkyrie": (
        "6c5e9d46d83f9cb644cc37d9651511102cc27ce539bed7024e8b14f1698aae29"
    ),
    "recovery_valkyrie": FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256,
}
FROZEN_PHASE_A_RESULT_SHA256 = {
    "original_valkyrie": (
        "c4e8b1d3d375c35f666f8b31c34ad7381be7119016071f739a873d817bcddca1"
    ),
    "reroute_valkyrie": (
        "3b0ba3c391523935f9470e2cadad2709c9249322ed25f70669c291d77c8ba6c3"
    ),
    "recovery_valkyrie": (
        "bfb0d1182a8e0797a6507b03942eb7f4fa3508931e5be84d70ca515e09d64ab2"
    ),
}
FROZEN_PHASE_A_SURVIVOR_SHA256 = {
    "original_valkyrie": (
        "95e59919dbabe5c9a3e6de18b459214be7c849840191455b08794b91fb299b77"
    ),
    "reroute_valkyrie": (
        "21635e3fe3ad5ae80b4be4e7801cd400b88284aff1ce358ffd1a9c970e82da2b"
    ),
    "recovery_valkyrie": (
        "235a4f5c70aa9322197329a572ea21af12ec36758e3afedb69fc8931ea27a628"
    ),
}
FROZEN_PHASE_A_SURVIVOR_TASK_COUNT = {
    "original_valkyrie": 91,
    "reroute_valkyrie": 45,
    "recovery_valkyrie": 134,
}
FROZEN_FORMAL_MANIFEST_SHA256 = (
    "e8aed1d26a0920bfef4964d495d86b69bbad666efb8d72e87462f297ca243855"
)
FROZEN_CAP16_ATHENA_MANIFEST_SHA256 = (
    "16e5f9ff04ed08ef9c29d8674021c11de3eed87b9da6a8c1e2ef68c6847ec0bb"
)
FROZEN_CAP16_PARENT_MANIFEST_SHA256 = (
    "490f2337d68fba626f34eed05abb64c772c752289bab31689b354240d2146876"
)
FROZEN_CAP16_PHASE_A_TASK_COUNT = 254
FROZEN_CAP16_PHASE_A_PACKAGE_AGGREGATE_SHA256 = (
    "b0ce4f33ad505df816d559a4260d8cc75f96a9914b9396e214fe9c2e3ecf5dee"
)
FROZEN_CAP16_PHASE_A_SURVIVOR_SHA256 = (
    "7ad21cb5ca4360689f00dca6f3a5eb7ec2385b9793315cfe5828892ded0ab49f"
)
FROZEN_CAP16_FORMAL_ARTIFACT_AGGREGATE_SHA256 = (
    "PENDING_AFTER_CAP16_FORMAL_COMPLETION"
)
FROZEN_CAP8_FORMAL_ARTIFACT_AGGREGATE_SHA256 = (
    "PENDING_AFTER_CAP8_R8_FORMAL_COMPLETION"
)
FROZEN_CAP8_FORMAL_PACKAGE_MANIFEST_SHA256 = (
    "a20797345df1bef6d5be5356906ee106b75b374b0d6cd2adfbc56cc5c3e65fef"
)
FROZEN_CAP8_FORMAL_PACKAGE_AGGREGATE_SHA256 = (
    "6c4592e158e037179d431f161c87cb494c7a22b00a9774d689ebe9b94b58f14c"
)
FROZEN_CAP8_FORMAL_TASK_COUNT = 270
FROZEN_CAP8_RESEARCH_HEAD = "558e54c5da5982db46ffb8fbca4704f4b6e03f21"
FROZEN_CAP8_RESEARCH_INVENTORY_SHA256 = (
    "a183f08ff2459ffa9102f1638d31183bb5c6b7fd7e8531deaf35b33e52c8f4f9"
)
FROZEN_CAP8_RUNTIME_CLOSURE = {
    "stock_lib_java_sha256":
        "eea0df062de5c8e3febe0d96b583741c140e79d3ae41a87a56d7be365b876f9d",
    "jdk_sha256":
        "867ff62e01a0936fc0a90ceae27338be1973559767ef0717896f8d64f780ece6",
    "ant_install": "/home/swear01/.local/opt/ant/usr",
    "ant_install_sha256":
        "52772e241e78a875fa00dea891eac2023d4f2be639a5f28a17dca81580f75e5b",
    "ant_version":
        "Apache Ant(TM) version 1.10.12 compiled on January 17 1970",
    "python_real": "/usr/bin/python3.10",
    "python_sha256":
        "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86",
    "python_version": "Python 3.10.12",
    "python_stdlib": "/usr/lib/python3.10",
    "python_stdlib_sha256":
        "eef7994f6b57cb0bbdb803ef6aadc0c1afbe61d444932eeef5dc5c114b6cf27b",
    "python_dist_packages": "/usr/lib/python3/dist-packages",
    "python_dist_packages_sha256":
        "0970024a48206a1937b5bfbf889335525b769b89a27ca7df25d793d7727b909c",
    "python_local_dist_packages":
        "/usr/local/lib/python3.10/dist-packages",
    "python_local_dist_packages_sha256":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "python_environment":
        '{"python_executable":"/usr/bin/python3.10","sys_path":'
        '["/var/tmp/swear01-cpachecker-paper/benchexec",'
        '"/usr/lib/python310.zip","/usr/lib/python3.10",'
        '"/usr/lib/python3.10/lib-dynload",'
        '"/usr/local/lib/python3.10/dist-packages",'
        '"/usr/lib/python3/dist-packages"],'
        '"yaml_file":"/usr/lib/python3/dist-packages/yaml/__init__.py",'
        '"yaml_version":"5.4.1"}',
    "benchexec_archive_sha256":
        "75e3332253429e6f9186352a255cd96c0aff6154a95e2fdd3b737c143ba018bc",
    "benchexec_version": "benchexec 3.35-dev",
}
PHASE_A_OPERATION = {
    "original_valkyrie": "deterministic_stratified_shard",
    "reroute_valkyrie": "deterministic_stratified_reroute",
    "recovery_valkyrie": "ordered_athena_recovery_merge",
}
FROZEN_CPACHECKER_VERSION = "4.2.2-2417-g1848f9eb59"
FROZEN_BENCHEXEC_GENERATOR = "BenchExec 3.35-dev"
FROZEN_TOOLMODULE = "benchexec.tools.cpachecker"
DISCOVERY_DISPLAY = "CPAchecker frozen stock hard-case discovery screen"
FORMAL_DISPLAY = "CPAchecker frozen stock hard-case formal measurement"
PROBE_DISPLAY = "VGuide no-candidate CEGAR eligibility probe"
FORMAL_REPETITION_PLAN_SCHEMA = "hard-case-formal-repetition-plan-v1"
CAP16_FORMAL_REPETITION_PLAN_SCHEMA = (
    "hard-case-cap16-formal-repetition-plan-v1"
)
FORMAL_TAINT_SCHEMA = "hard-case-formal-taint-v1"
CAP16_PROBE_TAINT_SCHEMA = "hard-case-cap16-cegar-probe-taint-v1"
CAP16_PROBE_PLAN_SCHEMA = "hard-case-cap16-cegar-probe-plan-v1"
CAP16_PROBE_INPUT_SCHEMA = "hard-case-cap16-cegar-probe-input-v1"
CAP16_PROBE_SUMMARY_SCHEMA = "hard-case-cap16-cegar-probe-summary-v1"
CAP8_PROBE_TAINT_SCHEMA = "hard-case-cap8-cegar-probe-taint-v1"
CAP8_PROBE_PLAN_SCHEMA = "hard-case-cap8-cegar-probe-plan-v1"
CAP8_PROBE_INPUT_SCHEMA = "hard-case-cap8-cegar-probe-input-v1"
CAP8_PROBE_SUMMARY_SCHEMA = "hard-case-cap8-cegar-probe-summary-v1"
STRICT_PROBE_STRATA = (
    ("cegar-eligible.csv", "cegar_eligible"),
    ("no-event.csv", "no_event"),
    ("hook-reached-without-loop-head.csv", "hook_reached_without_loop_head"),
    ("infrastructure-failure.csv", "infrastructure_failure"),
)
CAP16_PROBE_STRATA = STRICT_PROBE_STRATA
SCREEN_REPETITION_PLAN_SCHEMA = "hard-case-screen-repetition-plan-v1"
SCREEN_TAINT_SCHEMA = "hard-case-screen-taint-v1"
FORMAL_RECOVERY_PROTOCOL_SCHEMA = "hard-case-formal-recovery-protocol-v1"
FORMAL_RECOVERY_SEED_SCHEMA = "hard-case-formal-recovery-seed-ledger-v1"
FORMAL_RECOVERY_MIGRATION_SCHEMA = "hard-case-formal-recovery-migration-v1"
FORMAL_RECOVERY_BOOT_EVIDENCE_SCHEMA = "hard-case-formal-boot-evidence-v1"
FORMAL_RECOVERY_AUTHORIZATION_SCHEMA = (
    "hard-case-formal-attempt-authorization-v1"
)
FORMAL_RECOVERY_PREPARATION_SCHEMA = "hard-case-formal-shard-preparation-v1"
FORMAL_RECOVERY_LEDGER_SCHEMA = "hard-case-formal-attempt-ledger-v1"
FORMAL_RECOVERY_ABANDONMENT_SCHEMA = "hard-case-formal-pretask-abandonment-v1"
FORMAL_RECOVERY_REJECTION_SCHEMA = "hard-case-formal-invalid-evidence-v1"
FORMAL_RECOVERY_PLAN_SCHEMA = "hard-case-formal-recovery-plan-v1"
FORMAL_RUNTIME_COMMITS = {
    "cpachecker_commit": "1848f9eb597ca99a170fd98af8aad716743a2bfe",
    "sv_benchmarks_commit": "9cf9198156e4c8a6c517e474770158e1bb0b566d",
    "benchexec_commit": "edb95ed3a8478366b8bb89f8cdd1d9a6c5fa8c84",
    "jdk_sha256": (
        "867ff62e01a0936fc0a90ceae27338be1973559767ef0717896f8d64f780ece6"
    ),
}
FORMAL_TAINT_REASONS = {
    "foreign_p_core_contention",
    "interrupted_incomplete",
    "missing_load_monitor_coverage",
}
FORMAL_P_CORE_CPUS = tuple(range(16))
FORMAL_FOREIGN_CPU_PERCENT = 50.0
FORMAL_FOREIGN_CPU_SECONDS = 10.0
FORMAL_LOAD_SAMPLE_SECONDS = 1.0
FORMAL_LOAD_MONITOR_SCHEMA = "formal-p-core-load-monitor-v1"
FORMAL_ATTEMPT_SCHEMA = "hard-case-formal-attempt-complete-v4"
LEGACY_FORMAL_ATTEMPT_SCHEMA = "hard-case-formal-attempt-complete-v3"
FORMAL_PROCESS_IDENTITY_SCHEMA = "formal-owned-process-identity-v2"
LEGACY_FORMAL_PROCESS_IDENTITY_SCHEMA = "formal-owned-process-identity-v1"
FORMAL_RECOVERY_SELECTION_SCHEMA = "formal-attempt-recovery-selection-v1"
FORMAL_PROCESS_DESCRIPTOR_SCHEMA = "hard-case-formal-process-descriptor-v3"
PREVIOUS_FORMAL_PROCESS_DESCRIPTOR_SCHEMA = (
    "hard-case-formal-process-descriptor-v2"
)
LEGACY_FORMAL_PROCESS_DESCRIPTOR_SCHEMA = (
    "hard-case-formal-process-descriptor-v1"
)
FORMAL_P_CORE_LIST = "0,2,4,6,8,10,12,14"
FORMAL_PYYAML_FILE = "/usr/lib/python3/dist-packages/yaml/__init__.py"
PYTHON_RUNTIME_FLAGS = (
    "-I",
    "-S",
    "-B",
    "-X",
    "pycache_prefix=/dev/null",
)
EMPTY_PROVIDER_MODEL = "deterministic-empty-provider"
EMPTY_PROVIDER_RESPONSE_SHA256 = (
    "950ec9013b84aed3afe9761427511822630e80cd5f009e837389312830deba94"
)
BENCHEXEC_MODULE_COMMAND = (
    "import importlib.util,runpy,sys; from pathlib import Path; "
    "repository=sys.argv.pop(1); yaml_file=sys.argv.pop(1); "
    'spec=importlib.util.spec_from_file_location("yaml",yaml_file,'
    "submodule_search_locations=[str(Path(yaml_file).parent)]); "
    "assert spec is not None and spec.loader is not None; "
    "yaml=importlib.util.module_from_spec(spec); "
    'sys.modules["yaml"]=yaml; spec.loader.exec_module(yaml); '
    "sys.path.insert(0,repository); "
    'sys.argv[0]="benchexec"; '
    'runpy.run_module("benchexec.benchexec",run_name="__main__")'
)
LEGACY_BENCHEXEC_MODULE_COMMAND = (
    'import runpy,sys; sys.dont_write_bytecode=True; '
    'sys.pycache_prefix="/dev/null"; sys.path.insert(0,sys.argv.pop(1)); '
    'sys.argv[0]="benchexec"; '
    'runpy.run_module("benchexec.benchexec",run_name="__main__")'
)
LEGACY_CAP16_ATHENA_REPETITION_1 = {
    "label": "repetition-1",
    "source": (
        "provenance/abandoned/repetition-1-1785246981276501974"
    ),
    "quarantine": (
        "provenance/abandoned/"
        "repetition-1-superseded-zero-row-rerun"
    ),
    "abandoned_sha256": (
        "b360147d55d46bca4521db4058f87f0a041c149fdf12596f57040c5b62daf673"
    ),
    "selected_results_digest": (
        "96d1fede30dfabc38679de61df5f38a0d3e0b66c2e9131113daf55887ee5ba93"
    ),
    "displaced_results_digest": (
        "0bedef6ae6ff328da4a6bed8936fb6c25852b25cad3e6ecf6f452378846c963d"
    ),
    "selected_result_sha256": (
        "6cad08833bc31ce47e071af7af043275b801523b98abcd27f05c3a9e64916967"
    ),
    "displaced_result_sha256": (
        "de61373424e90c41d0b06d620a114bcdfa4e7c6887302b0f9584396b4ec9a665"
    ),
    "selected_complete_rows": 50,
    "displaced_complete_rows": 0,
    "result_rows": 224,
    "selected_provenance": {
        "machine-before-repetition-1.json": (
            "1c6fcb0018b00042fa1fd3eaa1dff6825d40861c3280677ec9d8451033aa735e"
        ),
        "repetition-1-benchexec.log": (
            "2be9e26f96256145519fc221053edac89554d903b76fa64bc27093a5b87bec08"
        ),
        "repetition-1-benchexec.process.json": (
            "f12e9e1ec07f5b53604e09b92b48cad7056eadd5df13f593e691fce5aec63325"
        ),
        "repetition-1-load-monitor.jsonl": (
            "a81a9f05bc6130b2b33b619e5db6bd9c28985eeaf821b8c3713492c2e9812cfe"
        ),
        "repetition-1-load-monitor.jsonl.pid": (
            "e4b46a84de9acf0c038cffe129665f16738eea8ae238a28d3f42513ecdd0a5ba"
        ),
        "repetition-1-load-monitor.jsonl.process.json": (
            "8cc90860985e2753ebef97696511aa01a2a60d1ddb2a521827607ede2ce91f9e"
        ),
        "repetition-1-process-descriptor.json": (
            "4bfb708e63b3c3155726a0c1a49eca8d3da50befc8b505242ae82cc1205cf548"
        ),
    },
    "displaced_provenance": {
        "machine-before-repetition-1.json": (
            "2e6e5b76cbf175417cc3f73d3d200294df4fed996c77b048c4f6202e84b9798e"
        ),
        "repetition-1-benchexec.log": (
            "f4a9d058e0a9375026a2d582e39b9ac704de26fdee57d4257813f37b94002e21"
        ),
        "repetition-1-benchexec.process.json": (
            "b29419ec44599455cd0955f3138368174bad6389739b180cba0c71a575921a11"
        ),
        "repetition-1-load-monitor.jsonl": (
            "1c63a7032aab15e17560dd807747f5cdfb05a8a7f8f58205a767ccadd3d8d50b"
        ),
        "repetition-1-load-monitor.jsonl.pid": (
            "bdc031d6dcb1556ab7f93c2b7627be649d96c8c934abd604bf02462253136009"
        ),
        "repetition-1-load-monitor.jsonl.process.json": (
            "26bdda190122627588aa96d45309f8139f8c0e077d39ea73cc368f8f0087f38c"
        ),
        "repetition-1-process-descriptor.json": (
            "1346e88627f19337e7409a7783c079235b21da70135d709838c66b5d7f37ad43"
        ),
    },
}
FROZEN_CAP16_ATHENA_V2_RECOVERY_SELECTION = {
    "label": "repetition-1-replacement-attempt-1",
    "role": "replacement",
    "repetition": 1,
    "captured_boot_id": "4e287d3c-8495-4da6-a0dd-b0b7de2b58d8",
    "result_directory": "results/repetition-1-replacement-attempt-1",
    "result_directory_digest": (
        "e2180b2dd7a9826616cc55455542add6f0694120bf99642a60019008e6ff5155"
    ),
    "result_directories": (
        "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
        "repetition-1-replacement-attempt-1.2026-07-29_04-46-16.logfiles",
    ),
    "files": {
        "definition": {
            "path": (
                "generated/repetition-1-replacement-attempt-1/"
                "hard-case-candidates.xml"
            ),
            "sha256": (
                "34e96a54f23ac11a5d82aac84a9db72432ebb1c59e05ef5dbe274771b2fc8766"
            ),
        },
        "result": {
            "path": (
                "results/repetition-1-replacement-attempt-1/"
                "hard-case-candidates.hard-case-dataset-v2-cap16-formal-"
                "athena-repetition-1-replacement-attempt-1."
                "2026-07-29_04-46-16.results.hard-case-candidates.official.xml"
            ),
            "sha256": (
                "06b98488f825be43a0fde6f4dc81993f3bafcd8459daaea316bd97c266aa0040"
            ),
        },
        "benchexec_log": {
            "path": (
                "provenance/repetition-1-replacement-attempt-1-benchexec.log"
            ),
            "sha256": (
                "46bb63eae4354f786e26d54eea8275adde32e2ac229275540f99ac28e2d96b84"
            ),
        },
        "benchexec_process": {
            "path": (
                "provenance/repetition-1-replacement-attempt-1-"
                "benchexec.process.json"
            ),
            "sha256": (
                "5c0f0d475c6b7267b91059c48b180e3983e89bce1d6d6af241063dff2fab3112"
            ),
        },
        "process_descriptor": {
            "path": (
                "provenance/repetition-1-replacement-attempt-1-"
                "process-descriptor.json"
            ),
            "sha256": (
                "ae49183bb0e334399748e27ac41c206335d4633af2cffc96e0c93a792441dda3"
            ),
        },
        "load_monitor": {
            "path": (
                "provenance/repetition-1-replacement-attempt-1-"
                "load-monitor.jsonl"
            ),
            "sha256": (
                "8639dfcee19656b22a4b2309d8061778a67523410b4a796f40d2f9f691aa278b"
            ),
        },
        "monitor_pid": {
            "path": (
                "provenance/repetition-1-replacement-attempt-1-"
                "load-monitor.jsonl.pid"
            ),
            "sha256": (
                "ecc33d65a19e02feeb1c4b8cbbdb042c147c56ecbfa9709b74cc13af2c55fe23"
            ),
        },
        "monitor_process": {
            "path": (
                "provenance/repetition-1-replacement-attempt-1-"
                "load-monitor.jsonl.process.json"
            ),
            "sha256": (
                "7c35eab1704cc6ce530ad6c009d0e77ccc1252559d4bd819253687e7d6517642"
            ),
        },
        "machine_before": {
            "path": (
                "provenance/machine-before-repetition-1-"
                "replacement-attempt-1.json"
            ),
            "sha256": (
                "f7e1206c6189c22a9602610ae1cb5e57c59187c4d22c34e528920b4bd31b1d3f"
            ),
        },
    },
    "closure_files": {
        (
            "generated/repetition-1-replacement-attempt-1/"
            "hard-case-candidates-official.set"
        ): "ac0c97d6ddd04ee815339e7fb8610c26fa44dd55ea16e0695b203923b2c50869",
        "repetition-1-taint.json": (
            "ed9c66b357231bf3dc1769d53bab67a4b34f97446604151626350bbf8d3c6f38"
        ),
    },
}
FROZEN_CAP16_ATHENA_ATTEMPT_2_V2_RECOVERY_SELECTION = {
    "label": "repetition-1-replacement-attempt-2",
    "role": "replacement",
    "repetition": 1,
    "captured_boot_id": "0c4e2e6e-0531-4a2d-a1b8-78ac0bdec433",
    "result_directory": "results/repetition-1-replacement-attempt-2",
    "result_directory_digest": (
        "bcf44a9f29da0cac7a01bd7290634e14d036dacdffa13dd1a23d0fe0b01de30d"
    ),
    "result_directories": (
        "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
        "repetition-1-replacement-attempt-2.2026-07-29_11-16-51.logfiles",
    ),
    "files": {
        "definition": {
            "path": (
                "generated/repetition-1-replacement-attempt-2/"
                "hard-case-candidates.xml"
            ),
            "sha256": (
                "38d73734e0663686379d072f6861e02991057ac3811c92f05892a73941db7fa7"
            ),
        },
        "result": {
            "path": (
                "results/repetition-1-replacement-attempt-2/"
                "hard-case-candidates.hard-case-dataset-v2-cap16-formal-"
                "athena-repetition-1-replacement-attempt-2."
                "2026-07-29_11-16-51.results.hard-case-candidates.official.xml"
            ),
            "sha256": (
                "c102ddc216d1d2cb1da6a94c7313ed7a7e953124f979417c420a9c16b346adff"
            ),
        },
        "benchexec_log": {
            "path": (
                "provenance/repetition-1-replacement-attempt-2-benchexec.log"
            ),
            "sha256": (
                "21281365e61455be0654f8b753e3a7bf145cf9e495c2eba81b2a37398277572b"
            ),
        },
        "benchexec_process": {
            "path": (
                "provenance/repetition-1-replacement-attempt-2-"
                "benchexec.process.json"
            ),
            "sha256": (
                "bc8f04f6421e457855d3bc3141286603bcbb294dbf12f99e0fcbca0ed4ba4f4d"
            ),
        },
        "process_descriptor": {
            "path": (
                "provenance/repetition-1-replacement-attempt-2-"
                "process-descriptor.json"
            ),
            "sha256": (
                "7abc54fce7fc2435eb451d448a9f4746887279267f8498f608a18e475f6f1e34"
            ),
        },
        "load_monitor": {
            "path": (
                "provenance/repetition-1-replacement-attempt-2-"
                "load-monitor.jsonl"
            ),
            "sha256": (
                "d0a345bd57770a5dc4c5bafdc86f6df3a2c5ed18e63679426dc2ce24a2840b99"
            ),
        },
        "monitor_pid": {
            "path": (
                "provenance/repetition-1-replacement-attempt-2-"
                "load-monitor.jsonl.pid"
            ),
            "sha256": (
                "79c86d8992e0d52db9d6fc54a5b22baed8ebbea5701a272bddc0d0280b79dc84"
            ),
        },
        "monitor_process": {
            "path": (
                "provenance/repetition-1-replacement-attempt-2-"
                "load-monitor.jsonl.process.json"
            ),
            "sha256": (
                "14019f93291f92ca4aeb85159c0893657936a4eb3d2c555de2df66e95887dff8"
            ),
        },
        "machine_before": {
            "path": (
                "provenance/machine-before-repetition-1-"
                "replacement-attempt-2.json"
            ),
            "sha256": (
                "c813ebbf71be9d334b59f7d56a378228854d3650da4327cb4c56ec2558dbdae0"
            ),
        },
    },
    "closure_files": {
        (
            "generated/repetition-1-replacement-attempt-2/"
            "hard-case-candidates-official.set"
        ): "fe5b7bd2d204d314d206ce53cd7f2386c307c7545d56d565bf7166398501443f",
        "repetition-1-replacement-attempt-1-taint.json": (
            "de54201e1cd2228de2752c8afdea3330daf407a62fe67e17a9de6075173e8115"
        ),
        (
            "provenance/attempts/"
            "repetition-1-replacement-attempt-1.json"
        ): "70d3e40b92669a4fa924c0773e5d167b0a043ae97631b9123314285144f63a50",
    },
}
FROZEN_CAP16_ATHENA_ATTEMPT_3_V2_RECOVERY_SELECTION = {
    "label": "repetition-1-replacement-attempt-3",
    "role": "replacement",
    "repetition": 1,
    "captured_boot_id": "c1551052-e3fb-4d61-850d-04817c261bee",
    "result_directory": "results/repetition-1-replacement-attempt-3",
    "result_directory_digest": (
        "7bebd0da3e0bfff4af8a4d5c6890294bf9514e8e5aedb41b15bd3e5cd8feb882"
    ),
    "result_directories": (
        "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
        "repetition-1-replacement-attempt-3.2026-07-29_15-35-43.logfiles",
    ),
    "files": {
        "definition": {
            "path": (
                "generated/repetition-1-replacement-attempt-3/"
                "hard-case-candidates.xml"
            ),
            "sha256": (
                "63f2eaa4794037c9b0bf7e6116269405afd2dd0288fe0c2dddfea7d95e91ef57"
            ),
        },
        "result": {
            "path": (
                "results/repetition-1-replacement-attempt-3/"
                "hard-case-candidates.hard-case-dataset-v2-cap16-formal-"
                "athena-repetition-1-replacement-attempt-3."
                "2026-07-29_15-35-43.results.hard-case-candidates.official.xml"
            ),
            "sha256": (
                "ea6288087da7efd4e29411725693380acc1e38749afc4fe83a9256ac9d776be4"
            ),
        },
        "benchexec_log": {
            "path": (
                "provenance/repetition-1-replacement-attempt-3-benchexec.log"
            ),
            "sha256": (
                "c5abe84944c47e25adfb3b84058a150b7b366c7c34317fc8a1e659e9c120ae1c"
            ),
        },
        "benchexec_process": {
            "path": (
                "provenance/repetition-1-replacement-attempt-3-"
                "benchexec.process.json"
            ),
            "sha256": (
                "a240c2c94218d66d482ac7fc5a1b308e1a8b8afa4acb3b728783b9c510b26a8e"
            ),
        },
        "process_descriptor": {
            "path": (
                "provenance/repetition-1-replacement-attempt-3-"
                "process-descriptor.json"
            ),
            "sha256": (
                "afc0cb8e41b55b5e75b599131a6a60d4bbee1cb12af09c9ba024ea9b3b9d329e"
            ),
        },
        "load_monitor": {
            "path": (
                "provenance/repetition-1-replacement-attempt-3-"
                "load-monitor.jsonl"
            ),
            "sha256": (
                "54709e59d59c998ef7fab2b305af7589b3fbc5e448e573722c7211ec2ca60b24"
            ),
        },
        "monitor_pid": {
            "path": (
                "provenance/repetition-1-replacement-attempt-3-"
                "load-monitor.jsonl.pid"
            ),
            "sha256": (
                "ac952b4c5f08d4cf55afa4259269d6f9bbc5d10c8aafed6e046a75df94fd2ee5"
            ),
        },
        "monitor_process": {
            "path": (
                "provenance/repetition-1-replacement-attempt-3-"
                "load-monitor.jsonl.process.json"
            ),
            "sha256": (
                "53e0dd53977b9a9701cfd9e32cf44840f4ae7596af4b3c3510952435ac4865a2"
            ),
        },
        "machine_before": {
            "path": (
                "provenance/machine-before-repetition-1-"
                "replacement-attempt-3.json"
            ),
            "sha256": (
                "54ab30d15209b86aecd3ce7a5b998e7517679b21d864579764c8774269bfebf6"
            ),
        },
    },
    "closure_files": {
        (
            "generated/repetition-1-replacement-attempt-3/"
            "hard-case-candidates-official.set"
        ): "7f7b9a3ac9920efa61e1dcbf7e3c13bc6da7034f47cde651a55a1f5d4f41d0da",
        "repetition-1-replacement-attempt-2-taint.json": (
            "027dc17df7f4ebda18ffb0d054d391738dea7658cfd23903f1b504b845d7b2af"
        ),
        (
            "provenance/attempts/"
            "repetition-1-replacement-attempt-2.json"
        ): "23aa10ed361e08efdc16f63a7ec160ffad6367c29cfa1cd095ec4fe3d00c01e1",
    },
}
FROZEN_CAP16_ATHENA_ATTEMPT_4_V2_RECOVERY_SELECTION = {
    "label": "repetition-1-replacement-attempt-4",
    "role": "replacement",
    "repetition": 1,
    "captured_boot_id": "42634c09-e311-4afb-9ff9-4eb49bbd07b6",
    "result_directory": "results/repetition-1-replacement-attempt-4",
    "result_directory_digest": (
        "ffa7a1fdbe39dd6cc19ee11eb3530cc031c5327c0391d12fbf27caa40bcecedb"
    ),
    "result_directories": (
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label41+token_ring.01.cil-1.yml"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label41+token_ring.01.cil-1.yml/output"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label41+token_ring.04.cil-1.yml"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label41+token_ring.04.cil-1.yml/output"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label41+token_ring.12.cil-2.yml"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label41+token_ring.12.cil-2.yml/output"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label43+token_ring.03.cil-2.yml"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label43+token_ring.03.cil-2.yml/output"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label45+token_ring.01.cil-1.yml"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label45+token_ring.01.cil-1.yml/output"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label45+token_ring.02.cil-1.yml"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label45+token_ring.02.cil-1.yml/output"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label45+token_ring.03.cil-2.yml"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label45+token_ring.03.cil-2.yml/output"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label46+token_ring.03.cil-2.yml"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label46+token_ring.03.cil-2.yml/output"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label49+token_ring.03.cil-2.yml"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/Problem05_label49+token_ring.03.cil-2.yml/output"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/pals_lcr.3.ufo.BOUNDED-6.pals+Problem12_label03.yml"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/pals_lcr.3.ufo.BOUNDED-6.pals+Problem12_label03.yml/output"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/pals_lcr.5.1.ufo.UNBOUNDED.pals+Problem12_label05.yml"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".files/hard-case-candidates/pals_lcr.5.1.ufo.UNBOUNDED.pals+Problem12_label05.yml/output"
        ),
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-4.2026-07-29_18-02-06"
            ".logfiles"
        ),
    ),
    "files": {
        "definition": {
            "path": (
                "generated/repetition-1-replacement-attempt-4/hard-case-candidates.xml"
            ),
            "sha256": (
                "0a0c118e750322d69471546c2bbd51dfd3b795f55512a36e1f6de19491568e7d"
            ),
        },
        "result": {
            "path": (
                "results/repetition-1-replacement-attempt-4/hard-case-candidates.hard-"
                "case-dataset-v2-cap16-formal-athena-repetition-1-replacement-attempt-"
                "4.2026-07-29_18-02-06.results.hard-case-candidates.official.xml"
            ),
            "sha256": (
                "72a95d9f1508ced6c7f3d431e9baa37329210ef7a4327a82562a946497e2c365"
            ),
        },
        "benchexec_log": {
            "path": "provenance/repetition-1-replacement-attempt-4-benchexec.log",
            "sha256": (
                "ed9d9b9547aea51b729bbc4b8369ebf7d9d3f946ef799510da98535e37b4170c"
            ),
        },
        "benchexec_process": {
            "path": (
                "provenance/repetition-1-replacement-attempt-4-benchexec.process.json"
            ),
            "sha256": (
                "f55d5cced1b50c24f90609bb5f6d10635edbcbc7666453471c1f62f322ae80dd"
            ),
        },
        "process_descriptor": {
            "path": (
                "provenance/repetition-1-replacement-attempt-4-process-descriptor.json"
            ),
            "sha256": (
                "5b3463e3eb9439b61739bf902a69664ec06af1f9898ca2a2b0c4a4a5d1703bcb"
            ),
        },
        "load_monitor": {
            "path": "provenance/repetition-1-replacement-attempt-4-load-monitor.jsonl",
            "sha256": (
                "a2d5bf46766c774bc19bc3db91ed34fc7189d855d0a2c611450a2cd19ffa9738"
            ),
        },
        "monitor_pid": {
            "path": (
                "provenance/repetition-1-replacement-attempt-4-load-monitor.jsonl.pid"
            ),
            "sha256": (
                "cec20bc2f9dc18bc8d79bc816b899ff19d1e56c3ddceca7b66deec2ab3e73b61"
            ),
        },
        "monitor_process": {
            "path": (
                "provenance/repetition-1-replacement-attempt-4-load-monitor.jsonl."
                "process.json"
            ),
            "sha256": (
                "3f4c08b9ca002287095d057db8eb87b7e853108534ba8331c5a304b29fa593a6"
            ),
        },
        "machine_before": {
            "path": "provenance/machine-before-repetition-1-replacement-attempt-4.json",
            "sha256": (
                "86a33bc64e2725b3bbce7e1f61c04cd4b52892dc5e1ca48597f20ba8a422c943"
            ),
        },
    },
    "closure_files": {
        (
            "generated/repetition-1-replacement-attempt-4/hard-case-candidates-"
            "official.set"
        ): (
            "061c70147f21aa7eebcefb9bfcecd23eda9930ea3862c07fdc8abde0e884758e"
        ),
        "provenance/attempts/repetition-1-replacement-attempt-3.json": (
            "97a3b0faba2d3b91d2db8baf1cc4fd4820f5c83fb9c26ca1c2238ab59f72f10f"
        ),
        "repetition-1-replacement-attempt-3-taint.json": (
            "d1a1f009f747b508ca4098c75278908203f8ed2560c09d50174edfbd33321492"
        ),
    },
}


FROZEN_CAP16_ATHENA_ATTEMPT_5_V2_RECOVERY_SELECTION = {
    "captured_boot_id": "81ffe4f0-858e-4028-983b-242c16b56907",
    "closure_files": {
        (
            "generated/repetition-1-replacement-attempt-5/"
            "hard-case-candidates-official.set"
        ): "03c1a920701f134c21c35e46d09abd430d01898cf2d4bf24b3684f6237cd9281",
        (
            "provenance/attempts/repetition-1-replacement-attempt-3.json"
        ): "97a3b0faba2d3b91d2db8baf1cc4fd4820f5c83fb9c26ca1c2238ab59f72f10f",
        (
            "repetition-1-replacement-attempt-3-taint.json"
        ): "d1a1f009f747b508ca4098c75278908203f8ed2560c09d50174edfbd33321492",
    },
    "files": {
        "benchexec_log": {
            "path": (
                "provenance/"
                "repetition-1-replacement-attempt-5-benchexec.log"
            ),
            "sha256": (
                "3593207d0594ce3b789c2de9a792c26fb34d94f6c7190fa0d23390042c53c098"
            ),
        },
        "benchexec_process": {
            "path": (
                "provenance/"
                "repetition-1-replacement-attempt-5-benchexec.process.json"
            ),
            "sha256": (
                "f846602ac45577ccfc0897b513e7296b3e105e5176a628d3d8fe914b88a4a51b"
            ),
        },
        "definition": {
            "path": (
                "generated/repetition-1-replacement-attempt-5/"
                "hard-case-candidates.xml"
            ),
            "sha256": (
                "756a5f79a309d804310a36a7eee8d5d70d6148ea52324e5005159e1bb7738285"
            ),
        },
        "load_monitor": {
            "path": (
                "provenance/"
                "repetition-1-replacement-attempt-5-load-monitor.jsonl"
            ),
            "sha256": (
                "a204371d08f485482007faa99a33afacf84aa390cfbb98d0db2522a335248b84"
            ),
        },
        "machine_before": {
            "path": (
                "provenance/"
                "machine-before-repetition-1-replacement-attempt-5.json"
            ),
            "sha256": (
                "eab9d3388f97e8c15295bc2758835f832bfdc3b11a8b8ef95184979812114b45"
            ),
        },
        "monitor_pid": {
            "path": (
                "provenance/"
                "repetition-1-replacement-attempt-5-load-monitor.jsonl.pid"
            ),
            "sha256": (
                "e58b794fb0a1043d32eea1d57a9b870318ab1ff8ee6e91bcdbb17f67d60ccdc7"
            ),
        },
        "monitor_process": {
            "path": (
                "provenance/repetition-1-replacement-attempt-5-"
                "load-monitor.jsonl.process.json"
            ),
            "sha256": (
                "d807e523511a0270f840c551b94fc3ac2461743a8a49221aa3748bbee267f791"
            ),
        },
        "process_descriptor": {
            "path": (
                "provenance/repetition-1-replacement-attempt-5-"
                "process-descriptor.json"
            ),
            "sha256": (
                "ad635af266491065409d26a2e996e88c1b6db6f6e826260ea337ac83098bf833"
            ),
        },
        "result": {
            "path": (
                "results/repetition-1-replacement-attempt-5/"
                "hard-case-candidates.hard-case-dataset-v2-cap16-formal-"
                "athena-repetition-1-replacement-attempt-5."
                "2026-07-29_22-07-48.results.hard-case-candidates."
                "official.xml"
            ),
            "sha256": (
                "2f01f7fc7e724999a1a1de06c2d46626c79e5af87e370815b5c06ee6650b2efd"
            ),
        },
    },
    "label": "repetition-1-replacement-attempt-5",
    "repetition": 1,
    "result_directories": [
        (
            "hard-case-candidates.hard-case-dataset-v2-cap16-formal-athena-"
            "repetition-1-replacement-attempt-5.2026-07-29_22-07-48.logfiles"
        ),
    ],
    "result_directory": "results/repetition-1-replacement-attempt-5",
    "result_directory_digest": (
        "eacc6d142d200749b01dac8796692d2fadb3c3c25a4859fa81fb6dfc9306e88b"
    ),
    "role": "replacement",
}
FROZEN_CAP16_ATHENA_ATTEMPT_5_V2_RECOVERY_SELECTION_SHA256 = (
    "97c6a7e4bcf013eef8ddc855b939f28ba223f630d2e088654f1eda533770ac54"
)
FROZEN_CAP16_ATHENA_ATTEMPT_5_FINAL_LOG_ONLY_PENDING_TASK = (
    "c/eca-programs/Problem102_label23.yml"
)


def strict_probe_profile(cohort):
  profiles = {
      "cap8": {
          "host": "valkyrie",
          "manifest_name": "candidate-manifest-cap8-probe.json",
          "input_schema": CAP8_PROBE_INPUT_SCHEMA,
          "plan_schema": CAP8_PROBE_PLAN_SCHEMA,
          "taint_schema": CAP8_PROBE_TAINT_SCHEMA,
          "summary_schema": CAP8_PROBE_SUMMARY_SCHEMA,
          "row_provenance_schema":
              "hard-case-cap8-cegar-probe-row-provenance-v1",
          "accepted_labels": {"stable_hard_solved", "stable_unsolved"},
          "operation": "cap8_zero_candidate_probe_input",
      },
      "cap16": {
          "host": "athena",
          "manifest_name": "candidate-manifest-cap16-probe.json",
          "input_schema": CAP16_PROBE_INPUT_SCHEMA,
          "plan_schema": CAP16_PROBE_PLAN_SCHEMA,
          "taint_schema": CAP16_PROBE_TAINT_SCHEMA,
          "summary_schema": CAP16_PROBE_SUMMARY_SCHEMA,
          "row_provenance_schema":
              "hard-case-cap16-cegar-probe-row-provenance-v1",
          "accepted_labels": {
              "stable_hard_solved",
              "stable_analysis_unsolved",
          },
          "operation": "cap16_zero_candidate_probe_input",
      },
  }
  try:
    return profiles[cohort]
  except KeyError as error:
    raise RuntimeError(f"unknown strict probe cohort: {cohort}") from error


def is_strict_probe_mode(mode):
  return mode in {"cap8-probe", "cap16-probe"}


def sha256_text(value):
  return hashlib.sha256(value.encode("utf-8")).hexdigest()


def family_name(component):
  return re.sub(r"[-_]?\d.*$", "", component) or component


def family_cap(candidates, limit):
  groups = collections.defaultdict(list)
  for candidate in candidates:
    key = (
        candidate["family"],
        candidate["seed_class"],
        candidate["expected_verdict"],
    )
    groups[key].append(candidate)
  selected = []
  for group in groups.values():
    selected.extend(
        sorted(group, key=lambda row: sha256_text(row["task"]))[:limit]
    )
  return sorted(selected, key=lambda row: row["task"])


def classify_repetitions(rows, hard_threshold):
  if any(row["category"] == "wrong" for row in rows):
    return "wrong_quarantine"
  if any(
      row.get("classification") == "infrastructure_or_manifest_failure"
      for row in rows
  ):
    return "infrastructure_failure"
  if all(row["category"] == "correct" for row in rows):
    cpu_times = [row["cpu_time_seconds"] for row in rows]
    if any(value is None for value in cpu_times):
      return "mixed"
    return (
        "stable_hard_solved"
        if statistics.median(cpu_times) > hard_threshold
        else "stable_solved_fast"
    )
  if all(is_analysis_unsolved(row) for row in rows):
    return "stable_analysis_unsolved"
  if all(row["category"] not in {"correct", "wrong"} for row in rows):
    return "verifier_failure_quarantine"
  return "mixed"


def is_analysis_unsolved(row):
  classification = row.get("classification")
  if classification in {"timeout", "out_of_memory"}:
    return True
  return classification == "unknown" and "unknown" in {
      row.get("category", "").strip().lower(),
      row.get("status", "").strip().lower(),
  }


def desc_inventory(source, root, desc_name):
  rows = []
  excluded = collections.Counter()
  for desc in sorted(root.rglob(desc_name)):
    text = desc.read_text(encoding="utf-8", errors="ignore")
    expected = (
        "true"
        if "VERIFICATION SUCCESSFUL" in text
        else "false"
        if "VERIFICATION FAILED" in text
        else None
    )
    if expected is None:
      excluded["no_binary_ground_truth"] += 1
      continue
    if expected == "false":
      excluded["failure_not_specific_to_reachability_property"] += 1
      continue
    sources = []
    for reference in SOURCE_REFERENCE.findall(text):
      candidate = desc.parent / reference
      if candidate.is_file() and candidate not in sources:
        sources.append(candidate)
    if len(sources) != 1:
      excluded["not_exactly_one_c_source"] += 1
      continue
    source_path = sources[0]
    program = source_path.read_text(encoding="utf-8", errors="ignore")
    if not LOOP.search(program):
      excluded["no_lexical_loop"] += 1
      continue
    if not ERROR_CALL.search(program):
      excluded["no_explicit_reachability_error_call"] += 1
      continue
    relative = source_path.relative_to(root)
    rows.append(
        {
            "source": source,
            "source_path": source_path,
            "source_relative": relative.as_posix(),
            "ground_truth_path": desc,
            "expected_verdict": expected,
            "family": family_name(relative.parts[0]),
            "license": SOURCE_LICENSES[source],
            "seed_class": "external_ground_truth",
            "task": f"external/{source}/{relative.with_suffix('.yml').as_posix()}",
        }
    )
  return rows, dict(sorted(excluded.items()))


def seahorn_inventory(root):
  rows = []
  excluded = collections.Counter()
  for source_path in sorted(root.rglob("*.c")):
    program = source_path.read_text(encoding="utf-8", errors="ignore")
    expected = (
        "true"
        if re.search(r"CHECK:\s*\^?unsat", program)
        else "false"
        if re.search(r"CHECK:\s*\^?sat", program)
        else None
    )
    if expected is None:
      excluded["no_binary_ground_truth"] += 1
      continue
    if not LOOP.search(program):
      excluded["no_lexical_loop"] += 1
      continue
    if not ERROR_CALL.search(program):
      excluded["no_explicit_reachability_error_call"] += 1
      continue
    relative = source_path.relative_to(root)
    rows.append(
        {
            "source": "seahorn",
            "source_path": source_path,
            "source_relative": relative.as_posix(),
            "ground_truth_path": source_path,
            "expected_verdict": expected,
            "family": family_name(relative.parts[0]),
            "license": SOURCE_LICENSES["seahorn"],
            "seed_class": "external_ground_truth",
            "task": f"external/seahorn/{relative.with_suffix('.yml').as_posix()}",
        }
    )
  return rows, dict(sorted(excluded.items()))


def load_svcomp_data(path):
  chunks = []
  recording = False
  with Path(path).open(encoding="utf-8") as source:
    for line in source:
      if not recording and line.startswith("const data = {"):
        recording = True
        chunks.append("{")
        continue
      if recording and line == "};\n":
        chunks.append("}")
        break
      if recording:
        chunks.append(line)
  if not chunks or chunks[-1] != "}":
    raise RuntimeError("SV-COMP result table has no complete embedded data object")
  return json.loads("".join(chunks))


def official_seed_inventory(sv_benchmarks, result_table):
  root = Path(sv_benchmarks).resolve()
  data = load_svcomp_data(result_table)
  tool_index = next(
      (
          index
          for index, tool in enumerate(data["tools"])
          if tool.get("benchmarkname") == "cpachecker"
      ),
      None,
  )
  if tool_index is None:
    raise RuntimeError("SV-COMP result table has no CPAchecker result")
  rows = []
  excluded = collections.Counter()
  for result_row in data["rows"]:
    relative, expected = result_row["id"][:2]
    task_path = root / "c" / relative
    if not task_path.is_file():
      excluded["task_missing_from_frozen_revision"] += 1
      continue
    metadata = baseline.task_metadata(task_path)
    if metadata is None or metadata["expected_verdict"] != expected:
      excluded["unsupported_or_changed_task"] += 1
      continue
    sources = [(task_path.parent / item).resolve() for item in metadata["input_files"]]
    if len(sources) != 1 or not sources[0].is_file():
      excluded["not_exactly_one_c_source"] += 1
      continue
    if not LOOP.search(sources[0].read_text(encoding="utf-8", errors="ignore")):
      excluded["no_lexical_loop"] += 1
      continue
    result = result_row["results"][tool_index]
    values = result.get("values", [])
    cpu_time = (
        float(values[1]["raw"])
        if len(values) > 1 and values[1].get("raw") not in {None, ""}
        else None
    )
    category = result.get("category", "")
    seed_class = (
        "hard_solved_seed"
        if category == "correct" and cpu_time is not None and cpu_time > 200
        else "unsolved_seed"
        if category in {"error", "unknown", "empty"}
        else None
    )
    if seed_class is None:
      excluded["not_hard_or_unsolved_in_seed_result"] += 1
      continue
    task = f"c/{relative}"
    rows.append(
        {
            "task": task,
            "task_path": task_path,
            "source_paths": sources,
            "expected_verdict": expected,
            "data_model": metadata["data_model"],
            "family": relative.split("/", 1)[0],
            "benchmark_set": f"svcomp:{relative.split('/', 1)[0]}",
            "source": "sv-benchmarks",
            "license": "per-file SPDX",
            "seed_class": seed_class,
            "seed_cpu_seconds": cpu_time,
            "seed_category": category,
        }
    )
  return rows, dict(sorted(excluded.items())), data["tools"][tool_index]


def prior_candidates(path, sv_benchmarks):
  root = Path(sv_benchmarks).resolve()
  rows = []
  with Path(path).open(newline="", encoding="utf-8") as source:
    for result in csv.DictReader(source):
      if result["category"] == "wrong" or (
          result["hard"] != "True" and result["unsolved"] != "True"
      ):
        continue
      task_path = root / result["task"]
      metadata = baseline.task_metadata(task_path)
      sources = [(task_path.parent / item).resolve() for item in metadata["input_files"]]
      relative = task_path.relative_to(root / "c").as_posix()
      rows.append(
          {
              "task": result["task"],
              "task_path": task_path,
              "source_paths": sources,
              "expected_verdict": metadata["expected_verdict"],
              "data_model": metadata["data_model"],
              "family": relative.split("/", 1)[0],
              "benchmark_set": f"svcomp:{relative.split('/', 1)[0]}",
              "source": "sv-benchmarks",
              "license": "per-file SPDX",
              "seed_class": "baseline_v1_candidate",
          }
      )
  return rows


def write_external_task(output_root, candidate, property_file):
  case_id = sha256_text(
      f"{candidate['source']}:{candidate['source_relative']}"
  )[:16]
  target_source = (
      output_root / "corpus/external" / candidate["source"] / f"{case_id}.c"
  )
  target_source.parent.mkdir(parents=True, exist_ok=True)
  shutil.copyfile(candidate["source_path"], target_source)
  task_path = target_source.with_suffix(".yml")
  relative_property = os.path.relpath(property_file, task_path.parent)
  task_path.write_text(
      "format_version: '2.0'\n"
      f"input_files: '{target_source.name}'\n"
      "properties:\n"
      f"  - property_file: '{relative_property}'\n"
      f"    expected_verdict: {candidate['expected_verdict']}\n"
      "options:\n"
      "  language: C\n"
      "  data_model: LP64\n",
      encoding="utf-8",
  )
  return f"external/{candidate['source']}/{case_id}.yml", task_path, target_source


def git_head(path):
  return subprocess.check_output(
      ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
  ).strip()


def command_inventory(args):
  output = Path(args.output_dir).resolve()
  output.mkdir(parents=True)
  sv_benchmarks = Path(args.sv_benchmarks).resolve()
  official, official_excluded, seed_tool = official_seed_inventory(
      sv_benchmarks, args.svcomp_results
  )
  prior = prior_candidates(args.prior_results, sv_benchmarks)
  prior_names = {row["task"] for row in prior}
  selected_official = family_cap(
      (row for row in official if row["task"] not in prior_names), args.official_family_cap
  )

  external_root = Path(args.external_root).resolve()
  external_inventories = []
  external_report = {}
  for name, relative, desc_name in (
      ("cbmc", "cbmc/regression/cbmc", "test.desc"),
      ("esbmc", "esbmc/regression", "test.desc"),
  ):
    rows, excluded = desc_inventory(name, external_root / relative, desc_name)
    external_inventories.extend(rows)
    external_report[name] = {"eligible": len(rows), "excluded": excluded}
  rows, excluded = seahorn_inventory(external_root / "seahorn/test")
  external_inventories.extend(rows)
  external_report["seahorn"] = {"eligible": len(rows), "excluded": excluded}
  selected_external = family_cap(external_inventories, args.external_family_cap)

  property_file = output / "corpus/properties/unreach-call.prp"
  property_file.parent.mkdir(parents=True, exist_ok=True)
  shutil.copyfile(sv_benchmarks / "c/properties/unreach-call.prp", property_file)
  candidates = {row["task"]: row for row in [*prior, *selected_official]}
  for row in selected_external:
    task, task_path, source_path = write_external_task(output, row, property_file)
    candidates[task] = {
        **row,
        "task": task,
        "task_path": task_path,
        "source_paths": [source_path],
        "data_model": "LP64",
        "benchmark_set": f"external:{row['source']}:{row['family']}",
    }
  manifest_rows = []
  for row in sorted(candidates.values(), key=lambda item: item["task"]):
    is_official = row["source"] == "sv-benchmarks"
    task_path = Path(row["task_path"])
    source_paths = [Path(path) for path in row["source_paths"]]
    path_root = sv_benchmarks if is_official else output
    ground_truth = row.get("ground_truth_path")
    manifest_rows.append(
        {
            key: value
            for key, value in {
                **row,
                "task_path": task_path.relative_to(path_root).as_posix(),
                "source_paths": [
                    path.relative_to(path_root).as_posix() for path in source_paths
                ],
                "task_sha256": baseline.sha256_file(task_path),
                "source_sha256": [
                    baseline.sha256_file(path) for path in source_paths
                ],
                "ground_truth_path": (
                    Path(ground_truth)
                    .relative_to(external_root / row["source"])
                    .as_posix()
                    if ground_truth
                    else ""
                ),
            }.items()
            if key not in {"source_path"}
        }
    )
  manifest = {
      "schema_version": "hard-case-candidate-v1",
      "task_count": len(manifest_rows),
      "selection_rule": {
          "stock_only": True,
          "hard_threshold": "median CPU time > 200 seconds",
          "repetitions": 2,
          "official_family_cap": args.official_family_cap,
          "external_family_cap": args.external_family_cap,
          "wrong_policy": "quarantine",
      },
      "repositories": {
          "sv-benchmarks": git_head(sv_benchmarks),
          **{
              source: git_head(external_root / source)
              for source in SOURCE_LICENSES
          },
      },
      "seed_result": {
          "source_url": (
              "https://sv-comp.sosy-lab.org/2026/results/results-verified/"
              "META_C.ReachSafety.table.html"
          ),
          "sha256": baseline.sha256_file(Path(args.svcomp_results)),
          "tool": seed_tool,
      },
      "inventory": {
          "official_seed_eligible": len(official),
          "official_seed_excluded": official_excluded,
          "external": external_report,
          "excluded_sources": {
              "code2inv": {
                  "revision": git_head(external_root / "code2inv"),
                  "license": "none found in frozen checkout",
                  "reason": "not distributable without license permission",
              },
              "verify-c-common": {
                  "revision": git_head(external_root / "verify-c-common"),
                  "license": "none found in frozen checkout",
                  "reason": "license and external stub semantics unresolved",
              },
              "ultimate": {
                  "revision": git_head(external_root / "ultimate"),
                  "license": "mixed per-file licensing",
                  "reason": "per-file provenance and duplicate normalization unresolved",
              },
          },
      },
      "corpus_files": [
          {
              "path": property_file.relative_to(output).as_posix(),
              "sha256": baseline.sha256_file(property_file),
          }
      ],
      "tasks": manifest_rows,
  }
  manifest_path = output / "candidate-manifest.json"
  manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
  print(manifest_path)


def render_stock(args, display, limits, rows=None):
  manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
  output = Path(args.output_dir).resolve()
  output.mkdir(parents=True, exist_ok=True)
  task_sets = write_task_sets(
      manifest["tasks"] if rows is None else rows,
      Path(args.manifest),
      args.sv_benchmarks,
      output,
  )
  root = benchmark_root(display, *limits)
  ET.SubElement(root, "resultfiles").text = "**/witness.*"
  for name, value in (
      ("--svcomp27", None),
      ("--heap", "10000M"),
      ("--benchmark", None),
      ("--timelimit", limits[0]),
  ):
    option = ET.SubElement(root, "option", {"name": name})
    if value:
      option.text = value
  write_run_definition(
      root,
      "hard-case-candidates",
      task_sets,
      args.property_file,
      Path(args.manifest).resolve().parent / "corpus/properties/unreach-call.prp",
  )
  benchmark = output / "hard-case-candidates.xml"
  write_xml(root, benchmark)
  print(benchmark)
  return benchmark


def command_render(args):
  render_stock(args, DISCOVERY_DISPLAY, ("120 s", "130 s", "140 s"))


def require_absent_or_empty_output(path):
  output = Path(path).resolve()
  if output.exists() and (
      not output.is_dir() or any(output.iterdir())
  ):
    raise RuntimeError(f"output directory must be absent or empty: {output}")


def command_render_formal(args):
  require_absent_or_empty_output(args.output_dir)
  manifest, _ = authenticate_formal_manifest(args)
  if not manifest["tasks"]:
    raise RuntimeError("formal Phase B skipped: authenticated host merge has no tasks")
  property_file = (
      Path(args.sv_benchmarks).resolve() / "c/properties/unreach-call.prp"
  )
  if args.property_file != str(property_file) or not property_file.is_file():
    raise RuntimeError("formal property file must be the frozen official property")
  benchmark = render_stock(args, FORMAL_DISPLAY, ("900 s", "910 s", "920 s"))
  validate_formal_definition(
      benchmark, args.manifest, manifest, args.sv_benchmarks
  )


def formal_replacement_result_manifest(args, primary, manifest, host):
  result_tasks = result_task_names(primary, manifest)
  label = primary.parent.name
  cap16_replacement = (
      hasattr(args, "phase_a_output")
      and host == "athena"
      and re.fullmatch(
          r"repetition-[12]-replacement-attempt-[1-9]\d*", label
      )
  )
  if cap16_replacement:
    output_root = primary.parents[2]
    record = validate_formal_attempt_marker(
        output_root / f"provenance/attempts/{label}.json",
        output_root,
        Path(args.manifest).resolve(),
        args.sv_benchmarks,
        host,
        "cap16",
    )
    if (
        primary.parent != output_root / f"results/{label}"
        or record["role"] != "replacement"
        or (output_root / record["files"]["result"]["path"]).resolve() != primary
        or record["result_tasks"] != sorted(result_tasks)
    ):
      raise RuntimeError(
          "cap-16 replacement result is not an authenticated prior attempt"
      )
    return (
        {task: manifest[task] for task in result_tasks},
        record["repetition"],
    )
  if set(result_tasks) == set(manifest):
    return manifest, None
  raise RuntimeError("formal replacement primary does not cover the full manifest")


def command_render_formal_replacement(args):
  require_absent_or_empty_output(args.output_dir)
  manifest, host = authenticate_formal_manifest(args)
  manifest_rows = baseline.load_task_manifest(args.manifest)
  primary = Path(args.primary_result).resolve()
  primary_hash = baseline.sha256_file(primary)
  primary_metadata = result_metadata(
      primary, FORMAL_DISPLAY, "900 s", allow_incomplete=True
  )
  if primary_metadata["host"] != host:
    raise RuntimeError("formal primary result must run on the merged manifest host")
  primary_subset, prior_repetition = formal_replacement_result_manifest(
      args, primary, manifest_rows, host
  )
  validate_result_run_topology(
      primary,
      primary_subset,
      args.sv_benchmarks,
  )
  taint_path = Path(args.taint_manifest).resolve()
  taint_data = json.loads(taint_path.read_text(encoding="utf-8"))
  tainted = validate_taint_manifest(
      taint_data,
      taint_data.get("repetition"),
      primary_hash,
      manifest_rows,
  )
  if (
      prior_repetition is not None
      and taint_data["repetition"] != prior_repetition
  ):
    raise RuntimeError(
        "formal taint repetition does not match its authenticated prior attempt"
    )
  if not tainted:
    raise RuntimeError("formal replacement requires at least one tainted task")
  if not set(tainted) <= set(primary_subset):
    raise RuntimeError("formal taint contains tasks absent from its result")
  primary_rows = baseline.parse_result_rows(primary, primary_subset, 200)
  missing = {
      row["task"] for row in primary_rows if not row_is_complete(row)
  }
  if missing - set(tainted):
    raise RuntimeError(
        f"incomplete primary rows are not tainted: {sorted(missing - set(tainted))}"
    )
  selected = sorted(
      (row for row in manifest["tasks"] if row["task"] in tainted),
      key=lambda row: row["task"],
  )
  property_file = (
      Path(args.sv_benchmarks).resolve() / "c/properties/unreach-call.prp"
  )
  if args.property_file != str(property_file) or not property_file.is_file():
    raise RuntimeError("formal property file must be the frozen official property")
  benchmark = render_stock(
      args,
      FORMAL_DISPLAY,
      ("900 s", "910 s", "920 s"),
      rows=selected,
  )
  replacement_manifest = {**manifest, "task_count": len(selected), "tasks": selected}
  validate_formal_definition(
      benchmark,
      args.manifest,
      replacement_manifest,
      args.sv_benchmarks,
  )


def command_render_screen_replacement(args):
  require_absent_or_empty_output(args.output_dir)
  manifest_path = Path(args.manifest).resolve()
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  host = manifest.get("derivation", {}).get("host")
  if host not in DISCOVERY_HOSTS:
    raise RuntimeError("screen manifest has no known host provenance")
  rows = baseline.load_task_manifest(manifest_path)
  primary = Path(args.primary_result).resolve()
  primary_hash = baseline.sha256_file(primary)
  metadata = result_metadata(
      primary, DISCOVERY_DISPLAY, "120 s", allow_incomplete=True
  )
  if metadata["host"] != host:
    raise RuntimeError("screen primary result does not match its manifest host")
  primary_tasks = result_task_names(primary, rows)
  primary_subset = {task: rows[task] for task in primary_tasks}
  validate_result_run_topology(
      primary, primary_subset, args.sv_benchmarks
  )
  tainted = validate_taint_manifest(
      json.loads(Path(args.taint_manifest).read_text(encoding="utf-8")),
      1,
      primary_hash,
      rows,
      SCREEN_TAINT_SCHEMA,
  )
  if not tainted:
    raise RuntimeError("screen replacement requires at least one tainted task")
  if not set(tainted) <= set(primary_tasks):
    raise RuntimeError("screen taint contains tasks absent from its result")
  missing = {
      row["task"]
      for row in baseline.parse_result_rows(primary, primary_subset, 200)
      if not row_is_complete(row)
  }
  if missing - set(tainted):
    raise RuntimeError(
        f"incomplete screen rows are not tainted: {sorted(missing - set(tainted))}"
    )
  selected = sorted(
      (row for row in manifest["tasks"] if row["task"] in tainted),
      key=lambda row: row["task"],
  )
  property_file = (
      Path(args.sv_benchmarks).resolve() / "c/properties/unreach-call.prp"
  )
  if args.property_file != str(property_file) or not property_file.is_file():
    raise RuntimeError("screen property file must be the frozen official property")
  benchmark = render_stock(
      args,
      DISCOVERY_DISPLAY,
      ("120 s", "130 s", "140 s"),
      rows=selected,
  )
  replacement_manifest = {
      **manifest,
      "task_count": len(selected),
      "tasks": selected,
  }
  validate_screen_definition(
      benchmark,
      manifest_path,
      replacement_manifest,
      args.sv_benchmarks,
  )


def write_task_sets(rows, manifest_path, sv_benchmarks, output):
  task_sets = {}
  for source_group, selected in (
      ("official", [row for row in rows if row["source"] == "sv-benchmarks"]),
      ("external", [row for row in rows if row["source"] != "sv-benchmarks"]),
  ):
    if not selected:
      continue
    task_set = output / f"hard-case-candidates-{source_group}.set"
    task_set.write_text(
        "\n".join(
            str(
                (
                    Path(sv_benchmarks).resolve()
                    if row["source"] == "sv-benchmarks"
                    else Path(manifest_path).resolve().parent
                )
                / row["task_path"]
            )
            for row in selected
        )
        + "\n",
        encoding="utf-8",
    )
    task_sets[source_group] = task_set
  return task_sets


def benchmark_root(display_name, time_limit, hard_time_limit, wall_time_limit):
  return ET.Element(
      "benchmark",
      {
          "tool": "cpachecker",
          "displayName": display_name,
          "timelimit": time_limit,
          "hardtimelimit": hard_time_limit,
          "walltimelimit": wall_time_limit,
          "memlimit": "15 GB",
          "cpuCores": "4",
      },
  )


def write_run_definition(
    root, name, task_sets, official_property, external_property
):
  run = ET.SubElement(root, "rundefinition", {"name": name})
  for source_group, property_file in (
      ("official", official_property),
      ("external", str(external_property)),
  ):
    if source_group not in task_sets:
      continue
    tasks = ET.SubElement(run, "tasks", {"name": source_group})
    ET.SubElement(tasks, "includesfile").text = str(task_sets[source_group])
    ET.SubElement(tasks, "propertyfile").text = str(property_file)


def write_xml(root, path):
  baseline.indent_xml(root)
  ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=True)
  with path.open("a", encoding="utf-8") as target:
    target.write("\n")


def result_metadata(path, display, time_limit, allow_incomplete=False):
  with baseline.open_result(Path(path)) as source:
    root = ET.parse(source).getroot()
  expected = {
      "tool": "CPAchecker",
      "version": FROZEN_CPACHECKER_VERSION,
      "toolmodule": FROZEN_TOOLMODULE,
      "generator": FROZEN_BENCHEXEC_GENERATOR,
      "displayName": display,
      "memlimit": "15000000000B",
      "timelimit": time_limit.replace(" ", ""),
      "cpuCores": "4",
      "block": "official",
      "name": "hard-case-candidates.official",
      "options": (
          f"--svcomp27 --heap 10000M --benchmark --timelimit {time_limit}"
      ),
  }
  error = root.get("error")
  incomplete_errors = {"incomplete", "interrupted"} if allow_incomplete else set()
  if (
      root.tag != "result"
      or (error is not None and error not in incomplete_errors)
      or any(root.get(name) != value for name, value in expected.items())
  ):
    raise RuntimeError("result metadata does not match the frozen stock protocol")
  hosts = [node.get("hostname") for node in root.findall("systeminfo")]
  if len(hosts) != 1 or not hosts[0]:
    raise RuntimeError("result must contain exactly one systeminfo hostname")
  metadata = {
      "host": hosts[0],
      "starttime": root.get("starttime"),
      "endtime": root.get("endtime"),
      "benchmarkname": root.get("benchmarkname"),
  }
  if (
      not metadata["starttime"]
      or (not metadata["endtime"] and error not in incomplete_errors)
      or not metadata["benchmarkname"]
  ):
    raise RuntimeError("result lacks a start time, end time, or benchmark name")
  metadata["incomplete"] = error in incomplete_errors
  return metadata


def probe_result_metadata(path, allow_incomplete=False):
  with baseline.open_result(Path(path)) as source:
    root = ET.parse(source).getroot()
  expected = {
      "tool": "CPAchecker",
      "toolmodule": FROZEN_TOOLMODULE,
      "generator": FROZEN_BENCHEXEC_GENERATOR,
      "displayName": PROBE_DISPLAY,
      "memlimit": "15000000000B",
      "timelimit": "900s",
      "cpuCores": "1",
      "block": "official",
      "name": "cegar-eligibility.official",
      "options": (
          "--predicateAnalysis-vguide --heap 10000M --timelimit 900 s "
          "--option vguide.enable=true --option vguide.provider=EMPTY"
      ),
  }
  error = root.get("error")
  if (
      root.tag != "result"
      or (error is not None and (not allow_incomplete or error != "incomplete"))
      or any(root.get(name) != value for name, value in expected.items())
      or not root.get("version")
  ):
    raise RuntimeError("probe result metadata does not match the zero-candidate protocol")
  hosts = [node.get("hostname") for node in root.findall("systeminfo")]
  if len(hosts) != 1 or not hosts[0]:
    raise RuntimeError(
        "probe result must contain exactly one systeminfo hostname"
    )
  metadata = {
      "host": hosts[0],
      "starttime": root.get("starttime"),
      "endtime": root.get("endtime"),
      "benchmarkname": root.get("benchmarkname"),
      "incomplete": error == "incomplete",
  }
  if (
      not metadata["starttime"]
      or (not metadata["endtime"] and error != "incomplete")
      or not metadata["benchmarkname"]
  ):
    raise RuntimeError("probe result lacks required timestamps or benchmark name")
  return metadata


def benchexec_path_representations(
    expected_path, sv_benchmarks, benchmark_definition, result_file
):
  expected = Path(expected_path).resolve()
  sv_benchmarks = Path(sv_benchmarks).resolve()
  representations = {expected.as_posix()}
  try:
    relative = expected.relative_to(sv_benchmarks).as_posix()
    representations.add(relative)
    representations.add(f"../../../../{sv_benchmarks.name}/{relative}")
  except ValueError:
    pass
  if benchmark_definition:
    relative = os.path.relpath(
        expected, Path(benchmark_definition).resolve().parent
    ).replace("\\", "/")
    representations.add(relative)
  relative = os.path.relpath(
      expected, Path(result_file).resolve().parent
  ).replace("\\", "/")
  representations.add(relative)
  return representations


def validate_result_run_topology(
    path, manifest, sv_benchmarks, benchmark_definition=None
):
  result_file = Path(path).resolve()
  with baseline.open_result(result_file) as source:
    root = ET.parse(source).getroot()
  expected_attributes = {
      "name",
      "files",
      "properties",
      "propertyFile",
      "expectedVerdict",
  }
  sv_benchmarks = Path(sv_benchmarks).resolve()
  official_property = sv_benchmarks / "c/properties/unreach-call.prp"
  property_representations = benchexec_path_representations(
      official_property, sv_benchmarks, benchmark_definition, result_file
  )
  for run in root.findall("run"):
    run_name = run.get("name", "").replace("\\", "/")
    matching_tasks = [
        name
        for name, candidate in manifest.items()
        if candidate["source"] == "sv-benchmarks"
        and run_name
        in benchexec_path_representations(
            sv_benchmarks / candidate["task_path"],
            sv_benchmarks,
            benchmark_definition,
            result_file,
        )
    ]
    if len(matching_tasks) != 1:
      raise RuntimeError(f"result task path is not exact: {run_name}")
    task_name = matching_tasks[0]
    task = manifest[task_name]
    if set(run.attrib) != expected_attributes:
      raise RuntimeError(f"result run topology is not exact: {task_name}")
    if run.get("properties") != "unreach-call":
      raise RuntimeError(f"result property is not unreach-call: {task_name}")
    property_file = run.get("propertyFile", "").replace("\\", "/")
    if (
        task["source"] != "sv-benchmarks"
        or property_file not in property_representations
    ):
      raise RuntimeError(f"result property file is not exact: {task_name}")
    if run.get("expectedVerdict", "").lower() != task["expected_verdict"]:
      raise RuntimeError(f"result expected verdict is not exact: {task_name}")
    files = run.get("files", "")
    if not files.startswith("[") or not files.endswith("]"):
      raise RuntimeError(f"result source-file topology is not exact: {task_name}")
    actual_files = [
        value.strip().replace("\\", "/")
        for value in files[1:-1].split(",")
        if value.strip()
    ]
    expected_files = [
        benchexec_path_representations(
            sv_benchmarks / source_path,
            sv_benchmarks,
            benchmark_definition,
            result_file,
        )
        for source_path in task["source_paths"]
    ]
    if len(actual_files) != len(expected_files) or any(
        actual not in expected
        for actual, expected in zip(actual_files, expected_files, strict=True)
    ):
      raise RuntimeError(f"result source files do not match manifest: {task_name}")


def xml_shape(node):
  return (
      node.tag,
      tuple(sorted(node.attrib.items())),
      (node.text or "").strip(),
      tuple(xml_shape(child) for child in node),
  )


def validate_stock_definition(
    path, manifest_path, manifest, sv_benchmarks, display, limits
):
  time_limit, hard_time_limit, wall_time_limit = limits
  root = ET.parse(path).getroot()
  expected_attributes = {
      "tool": "cpachecker",
      "displayName": display,
      "timelimit": time_limit,
      "hardtimelimit": hard_time_limit,
      "walltimelimit": wall_time_limit,
      "memlimit": "15 GB",
      "cpuCores": "4",
  }
  if root.tag != "benchmark" or root.attrib != expected_attributes:
    raise RuntimeError("stock benchmark metadata does not match the fixed limits")
  definition_dir = Path(path).resolve().parent
  groups = {
      "official": [
          row for row in manifest["tasks"] if row["source"] == "sv-benchmarks"
      ],
      "external": [
          row for row in manifest["tasks"] if row["source"] != "sv-benchmarks"
      ],
  }
  task_sets = {
      group: definition_dir / f"hard-case-candidates-{group}.set"
      for group, rows in groups.items()
      if rows
  }
  include_values = [
      node.text for node in root.findall(".//includesfile")
  ]
  portable = bool(include_values) and all(
      value == Path(value).name for value in include_values
  )
  definition_task_sets = {
      group: path.name if portable else path
      for group, path in task_sets.items()
  }
  expected = benchmark_root(display, *limits)
  ET.SubElement(expected, "resultfiles").text = "**/witness.*"
  for name, value in (
      ("--svcomp27", None),
      ("--heap", "10000M"),
      ("--benchmark", None),
      ("--timelimit", time_limit),
  ):
    option = ET.SubElement(expected, "option", {"name": name})
    if value:
      option.text = value
  write_run_definition(
      expected,
      "hard-case-candidates",
      definition_task_sets,
      (
          "c/properties/unreach-call.prp"
          if portable
          else Path(sv_benchmarks).resolve()
          / "c/properties/unreach-call.prp"
      ),
      Path(manifest_path).resolve().parent / "corpus/properties/unreach-call.prp",
  )
  if xml_shape(root) != xml_shape(expected):
    raise RuntimeError("stock benchmark definition topology is not frozen")
  for group, task_set in task_sets.items():
    expected_tasks = []
    for row in groups[group]:
      if portable and row["source"] == "sv-benchmarks":
        expected_tasks.append(row["task_path"])
      else:
        expected_tasks.append(str(
            (
                Path(sv_benchmarks).resolve()
                if row["source"] == "sv-benchmarks"
                else Path(manifest_path).resolve().parent
            )
            / row["task_path"]
        ))
    if task_set.read_text(encoding="utf-8").splitlines() != expected_tasks:
      raise RuntimeError("stock benchmark task set does not match the host manifest")


def validate_formal_definition(path, manifest_path, manifest, sv_benchmarks):
  root = ET.parse(path).getroot()
  if root.attrib != {
      "tool": "cpachecker",
      "displayName": FORMAL_DISPLAY,
      "timelimit": "900 s",
      "hardtimelimit": "910 s",
      "walltimelimit": "920 s",
      "memlimit": "15 GB",
      "cpuCores": "4",
  }:
    raise RuntimeError("formal benchmark metadata is not fixed at 900/910/920")
  validate_stock_definition(
      path,
      manifest_path,
      manifest,
      sv_benchmarks,
      FORMAL_DISPLAY,
      ("900 s", "910 s", "920 s"),
  )


def validate_screen_definition(path, manifest_path, manifest, sv_benchmarks):
  validate_stock_definition(
      path,
      manifest_path,
      manifest,
      sv_benchmarks,
      DISCOVERY_DISPLAY,
      ("120 s", "130 s", "140 s"),
  )


def render_probe(manifest_path, manifest, selected, sv_benchmarks, property_file, output):
  output = Path(output).resolve()
  require_absent_or_empty_output(output)
  output.mkdir(parents=True, exist_ok=True)
  task_sets = write_task_sets(
      selected, manifest_path, sv_benchmarks, output
  )
  root = benchmark_root(
      PROBE_DISPLAY, "900 s", "910 s", "920 s"
  )
  root.set("cpuCores", "1")
  ET.SubElement(root, "resultfiles").text = "**/vguide-telemetry.json"
  for name, value in (
      ("--predicateAnalysis-vguide", None),
      ("--heap", "10000M"),
      ("--timelimit", "900 s"),
      ("--option", "vguide.enable=true"),
      ("--option", "vguide.provider=EMPTY"),
  ):
    option = ET.SubElement(root, "option", {"name": name})
    if value:
      option.text = value
  write_run_definition(
      root,
      "cegar-eligibility",
      task_sets,
      property_file,
      Path(manifest_path).resolve().parent / "corpus/properties/unreach-call.prp",
  )
  benchmark = output / "cegar-eligibility.xml"
  write_xml(root, benchmark)
  subset = {
      **manifest,
      "task_count": len(selected),
      "tasks": selected,
  }
  validate_probe_definition(
      benchmark, manifest_path, subset, sv_benchmarks
  )
  print(benchmark)


def validate_probe_definition(path, manifest_path, manifest, sv_benchmarks):
  root = ET.parse(path).getroot()
  expected = benchmark_root(
      PROBE_DISPLAY, "900 s", "910 s", "920 s"
  )
  expected.set("cpuCores", "1")
  ET.SubElement(expected, "resultfiles").text = "**/vguide-telemetry.json"
  for name, value in (
      ("--predicateAnalysis-vguide", None),
      ("--heap", "10000M"),
      ("--timelimit", "900 s"),
      ("--option", "vguide.enable=true"),
      ("--option", "vguide.provider=EMPTY"),
  ):
    option = ET.SubElement(expected, "option", {"name": name})
    if value:
      option.text = value
  definition_dir = Path(path).resolve().parent
  groups = {
      "official": [
          row for row in manifest["tasks"] if row["source"] == "sv-benchmarks"
      ],
      "external": [
          row for row in manifest["tasks"] if row["source"] != "sv-benchmarks"
      ],
  }
  task_sets = {
      group: definition_dir / f"hard-case-candidates-{group}.set"
      for group, rows in groups.items()
      if rows
  }
  write_run_definition(
      expected,
      "cegar-eligibility",
      task_sets,
      Path(sv_benchmarks).resolve() / "c/properties/unreach-call.prp",
      Path(manifest_path).resolve().parent
      / "corpus/properties/unreach-call.prp",
  )
  if xml_shape(root) != xml_shape(expected):
    raise RuntimeError("probe benchmark definition topology is not frozen")
  for group, task_set in task_sets.items():
    expected_tasks = [
        str(
            (
                Path(sv_benchmarks).resolve()
                if row["source"] == "sv-benchmarks"
                else Path(manifest_path).resolve().parent
            )
            / row["task_path"]
        )
        for row in groups[group]
    ]
    if task_set.read_text(encoding="utf-8").splitlines() != expected_tasks:
      raise RuntimeError("probe task set does not match the authenticated manifest")


def command_render_probe(args):
  manifest_path = Path(args.manifest).resolve()
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  details = {row["task"]: row for row in manifest["tasks"]}
  with Path(args.hard_portfolio).open(newline="", encoding="utf-8") as source:
    rows = list(csv.DictReader(source))
  tasks = [row["task"] for row in rows]
  if (
      len(tasks) != len(set(tasks))
      or any(task not in details for task in tasks)
      or not tasks
  ):
    raise RuntimeError("probe hard portfolio is empty, duplicated, or outside manifest")
  render_probe(
      manifest_path,
      manifest,
      [details[task] for task in tasks],
      args.sv_benchmarks,
      args.property_file,
      args.output_dir,
  )


def render_strict_probe(args, cohort):
  _, manifest_path, manifest, hard, _ = validate_strict_probe_input(
      args.probe_input, args.sv_benchmarks, cohort
  )
  details = {row["task"]: row for row in manifest["tasks"]}
  render_probe(
      manifest_path,
      manifest,
      [details[row["task"]] for row in hard],
      args.sv_benchmarks,
      args.property_file,
      args.output_dir,
  )


def command_render_cap8_probe(args):
  render_strict_probe(args, "cap8")


def command_render_cap16_probe(args):
  render_strict_probe(args, "cap16")


def render_strict_probe_replacement(args, cohort):
  profile = strict_probe_profile(cohort)
  _, manifest_path, manifest, _, _ = validate_strict_probe_input(
      args.probe_input, args.sv_benchmarks, cohort
  )
  by_name = baseline.load_task_manifest(manifest_path)
  result = Path(args.primary_result).resolve()
  tainted = validate_taint_manifest(
      json.loads(Path(args.taint_manifest).read_text(encoding="utf-8")),
      1,
      baseline.sha256_file(result),
      by_name,
      profile["taint_schema"],
  )
  if not tainted:
    raise RuntimeError("probe replacement requires at least one tainted task")
  result_tasks = set(result_task_names(result, by_name))
  if not set(tainted) <= result_tasks:
    raise RuntimeError("probe replacement taint is outside its result")
  selected = sorted(
      (
          row for row in manifest["tasks"]
          if row["task"] in tainted
      ),
      key=lambda row: row["task"],
  )
  render_probe(
      manifest_path,
      manifest,
      selected,
      args.sv_benchmarks,
      args.property_file,
      args.output_dir,
  )


def command_render_cap8_probe_replacement(args):
  render_strict_probe_replacement(args, "cap8")


def command_render_cap16_probe_replacement(args):
  render_strict_probe_replacement(args, "cap16")


def split_for_family(family):
  bucket = int(sha256_text(family)[:8], 16) % 10
  return "development" if bucket < 6 else "validation" if bucket < 8 else "heldout"


def manifest_subset(manifest, tasks, derivation):
  selected = set(tasks)
  rows = [row for row in manifest["tasks"] if row["task"] in selected]
  if len(rows) != len(selected):
    raise RuntimeError("subset contains tasks absent from the input manifest")
  result = {
      **{key: value for key, value in manifest.items() if key != "license_audit"},
      "schema_version": "hard-case-candidate-v2-derived",
      "task_count": len(rows),
      "derivation": derivation,
      "tasks": rows,
  }
  if "license_audit" in manifest:
    source_sha256 = derivation.get("source_manifest_sha256")
    if not source_sha256:
      raise RuntimeError("derived audited manifest lacks its source manifest hash")
    audit = manifest["license_audit"]
    result["parent_license_audit"] = {
        "manifest_sha256": source_sha256,
        "included_task_count": audit["included_task_count"],
        "excluded_task_count": audit["excluded_task_count"],
        "selection_independent_of_verifier_outcomes": audit[
            "selection_independent_of_verifier_outcomes"
        ],
        "task_license_evidence_preserved": True,
    }
  return result


def stratified_shards(rows, hosts=DISCOVERY_HOSTS):
  hosts = tuple(hosts)
  if not hosts or len(hosts) != len(set(hosts)):
    raise RuntimeError("shard hosts must be nonempty and unique")
  groups = collections.defaultdict(list)
  for row in rows:
    groups[
        (row["family"], row["seed_class"], row["expected_verdict"])
    ].append(row)
  counts = {host: collections.Counter() for host in hosts}
  shards = {host: [] for host in hosts}
  host_order = {host: index for index, host in enumerate(hosts)}
  for stratum, tasks in sorted(
      groups.items(), key=lambda item: (-len(item[1]), item[0])
  ):
    family, seed, verdict = stratum
    for row in sorted(
        tasks, key=lambda item: (sha256_text(item["task"]), item["task"])
    ):
      host = min(
          hosts,
          key=lambda candidate: (
              counts[candidate][("stratum", stratum)],
              counts[candidate][("family", family)],
              counts[candidate][("seed", seed)],
              counts[candidate][("verdict", verdict)],
              counts[candidate][("total",)],
              host_order[candidate],
          ),
      )
      shards[host].append(row)
      counts[host][("stratum", stratum)] += 1
      counts[host][("family", family)] += 1
      counts[host][("seed", seed)] += 1
      counts[host][("verdict", verdict)] += 1
      counts[host][("total",)] += 1
  return shards


def requested_shard_hosts(args):
  hosts = tuple(getattr(args, "host", None) or DISCOVERY_HOSTS)
  if (
      not hosts
      or len(hosts) != len(set(hosts))
      or any(host not in DISCOVERY_HOSTS for host in hosts)
  ):
    raise RuntimeError("shard hosts must be known, nonempty, and unique")
  return hosts


def validate_shard_partition(rows, shards, hosts=DISCOVERY_HOSTS):
  hosts = tuple(hosts)
  expected = stratified_shards(rows, hosts)
  input_rows = {row["task"]: row for row in rows}
  actual_tasks = [
      row["task"] for host in hosts for row in shards.get(host, [])
  ]
  if len(actual_tasks) != len(set(actual_tasks)):
    raise RuntimeError("shard partition contains overlapping tasks")
  if set(actual_tasks) != set(input_rows):
    raise RuntimeError("shard partition contains missing or unexpected tasks")
  for host in hosts:
    actual = {row["task"]: row for row in shards.get(host, [])}
    if any(input_rows[task] != row for task, row in actual.items()):
      raise RuntimeError(f"shard partition contains changed task records: {host}")
    if set(actual) != {row["task"] for row in expected[host]}:
      raise RuntimeError(f"shard partition differs from recomputed assignment: {host}")


def command_difference(args):
  hosts = requested_shard_hosts(args)
  full_path = Path(args.manifest).resolve()
  excluded_path = Path(args.exclude_manifest).resolve()
  full = validate_manifest(full_path, args.sv_benchmarks)
  excluded = validate_manifest(excluded_path, args.sv_benchmarks)
  full_rows = {row["task"]: row for row in full["tasks"]}
  for row in excluded["tasks"]:
    if full_rows.get(row["task"]) != row:
      raise RuntimeError(
          f"excluded task is absent or differs from full manifest: {row['task']}"
      )
  excluded_tasks = {row["task"] for row in excluded["tasks"]}
  tasks = sorted(set(full_rows) - excluded_tasks)
  full_sha256 = baseline.sha256_file(full_path)
  output = Path(args.output_dir).resolve()
  if output.exists() and any(output.iterdir()):
    raise RuntimeError(f"output directory must be absent or empty: {output}")
  output.mkdir(parents=True, exist_ok=True)
  shutil.copytree(full_path.parent / "corpus", output / "corpus")
  derivation = {
      "operation": "difference",
      "source_manifest_sha256": full_sha256,
      "excluded_manifest_sha256": baseline.sha256_file(excluded_path),
      "selection_independent_of_verifier_outcomes": True,
  }
  difference = manifest_subset(full, tasks, derivation)
  difference_path = output / "candidate-manifest.json"
  difference_path.write_text(
      json.dumps(difference, indent=2) + "\n", encoding="utf-8"
  )
  difference_sha256 = baseline.sha256_file(difference_path)
  assigned = stratified_shards(difference["tasks"], hosts)
  shards = {}
  shard_manifests = {}
  for host in hosts:
    host_tasks = [row["task"] for row in assigned[host]]
    shard = manifest_subset(
        full,
        host_tasks,
        {
            "operation": "deterministic_stratified_shard",
            "source_manifest_sha256": full_sha256,
            "parent_manifest_sha256": difference_sha256,
            "hosts": list(hosts),
            "host": host,
            "algorithm": (
                "strata (family,seed_class,expected_verdict) by (-size,key); "
                "tasks by SHA-256(task); lexicographic least host counts for "
                "stratum,family,seed,verdict,total,host-order"
            ),
            "selection_independent_of_verifier_outcomes": True,
        },
    )
    shard_manifests[host] = shard
    path = output / f"candidate-manifest-{host}.json"
    path.write_text(json.dumps(shard, indent=2) + "\n", encoding="utf-8")
    shards[host] = {
        "task_count": len(host_tasks),
        "sha256": baseline.sha256_file(path),
    }
  validate_shard_partition(
      difference["tasks"],
      {host: shard["tasks"] for host, shard in shard_manifests.items()},
      hosts,
  )
  print(
      json.dumps(
          {
              "task_count": len(tasks),
              "sha256": difference_sha256,
              "shards": shards,
          },
          sort_keys=True,
      )
  )


def command_validate_shards(args):
  hosts = requested_shard_hosts(args)
  manifest_path = Path(args.manifest).resolve()
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  parent_sha256 = baseline.sha256_file(manifest_path)
  shards = {}
  for path in args.shard_manifest:
    shard = validate_manifest(path, args.sv_benchmarks)
    derivation = shard.get("derivation", {})
    host = derivation.get("host")
    if host not in hosts or host in shards:
      raise RuntimeError(f"invalid or duplicate shard host: {host}")
    if derivation.get("operation") != "deterministic_stratified_shard":
      raise RuntimeError(f"invalid shard operation: {host}")
    if derivation.get("hosts") != list(hosts):
      raise RuntimeError(f"invalid shard host list: {host}")
    if derivation.get("parent_manifest_sha256") != parent_sha256:
      raise RuntimeError(f"invalid shard parent manifest hash: {host}")
    shards[host] = shard["tasks"]
  validate_shard_partition(manifest["tasks"], shards, hosts)
  print(json.dumps({"task_count": manifest["task_count"], "valid": True}))


def validate_cthulhu_parent(manifest_path, sv_benchmarks):
  manifest_path = Path(manifest_path).resolve()
  if baseline.sha256_file(manifest_path) != FROZEN_CTHULHU_MANIFEST_SHA256:
    raise RuntimeError("Cthulhu parent manifest hash is not frozen r3 input")
  manifest = validate_manifest(manifest_path, sv_benchmarks)
  derivation = manifest.get("derivation", {})
  required = {
      "operation": "deterministic_stratified_shard",
      "hosts": list(DISCOVERY_HOSTS),
      "host": "cthulhu",
      "selection_independent_of_verifier_outcomes": True,
  }
  for field, expected in required.items():
    if derivation.get(field) != expected:
      raise RuntimeError(f"invalid Cthulhu parent provenance: {field}")
  return manifest


def reroute_derivation(parent):
  return {
      "operation": "deterministic_stratified_reroute",
      "parent_manifest_sha256": FROZEN_CTHULHU_MANIFEST_SHA256,
      "source_host": "cthulhu",
      "source_derivation": parent["derivation"],
      "hosts": list(REROUTE_HOSTS),
      "algorithm": (
          "strata (family,seed_class,expected_verdict) by (-size,key); "
          "tasks by SHA-256(task); lexicographic least host counts for "
          "stratum,family,seed,verdict,total,host-order"
      ),
      "selection_independent_of_verifier_outcomes": True,
  }


def command_reroute_cthulhu(args):
  parent_path = Path(args.manifest).resolve()
  parent = validate_cthulhu_parent(parent_path, args.sv_benchmarks)
  output = Path(args.output_dir).resolve()
  if output.exists() and any(output.iterdir()):
    raise RuntimeError(f"output directory must be absent or empty: {output}")
  output.mkdir(parents=True, exist_ok=True)
  shutil.copytree(parent_path.parent / "corpus", output / "corpus")
  assigned = stratified_shards(parent["tasks"], REROUTE_HOSTS)
  manifests = {}
  report = {}
  for host in REROUTE_HOSTS:
    derivation = {**reroute_derivation(parent), "host": host}
    manifest = manifest_subset(
        parent, [row["task"] for row in assigned[host]], derivation
    )
    path = output / f"candidate-manifest-{host}.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifests[host] = manifest
    report[host] = {
        "task_count": manifest["task_count"],
        "sha256": baseline.sha256_file(path),
    }
  validate_shard_partition(
      parent["tasks"],
      {host: manifest["tasks"] for host, manifest in manifests.items()},
      REROUTE_HOSTS,
  )
  print(
      json.dumps(
          {"parent_task_count": parent["task_count"], "reroutes": report},
          sort_keys=True,
      )
  )


def command_validate_reroute(args):
  parent = validate_cthulhu_parent(args.manifest, args.sv_benchmarks)
  reroutes = {}
  base_derivation = reroute_derivation(parent)
  for path in args.reroute_manifest:
    reroute = validate_manifest(path, args.sv_benchmarks)
    derivation = reroute.get("derivation", {})
    host = derivation.get("host")
    if host not in REROUTE_HOSTS or host in reroutes:
      raise RuntimeError(f"invalid or duplicate reroute host: {host}")
    expected_derivation = {**base_derivation, "host": host}
    if derivation != expected_derivation:
      raise RuntimeError(f"invalid reroute provenance: {host}")
    expected_manifest = manifest_subset(
        parent, [row["task"] for row in reroute["tasks"]], expected_derivation
    )
    if reroute != expected_manifest:
      raise RuntimeError(f"reroute contains changed provenance or rows: {host}")
    reroutes[host] = reroute["tasks"]
  if set(reroutes) != set(REROUTE_HOSTS):
    raise RuntimeError("reroute manifests do not contain both fixed hosts")
  validate_shard_partition(parent["tasks"], reroutes, REROUTE_HOSTS)
  print(json.dumps({"task_count": parent["task_count"], "valid": True}))


def athena_recovery_manifest(original, reroute):
  excluded = {"task_count", "tasks", "derivation"}
  if (
      {key: value for key, value in original.items() if key not in excluded}
      != {key: value for key, value in reroute.items() if key not in excluded}
  ):
    raise RuntimeError("Athena recovery parents have different corpus metadata")
  tasks = [*original["tasks"], *reroute["tasks"]]
  names = [row["task"] for row in tasks]
  if len(names) != len(set(names)):
    raise RuntimeError("Athena recovery parents contain overlapping tasks")
  return {
      **original,
      "task_count": len(tasks),
      "tasks": tasks,
      "derivation": {
          "operation": "ordered_athena_recovery_merge",
          "host": "valkyrie",
          "hosts": ["valkyrie"],
          "parents": [
              {
                  "manifest_sha256": FROZEN_ATHENA_MANIFEST_SHA256,
                  "task_count": original["task_count"],
                  "derivation": original["derivation"],
              },
              {
                  "manifest_sha256": FROZEN_ATHENA_REROUTE_MANIFEST_SHA256,
                  "task_count": reroute["task_count"],
                  "derivation": reroute["derivation"],
              },
          ],
          "algorithm": (
              "original Athena rows followed by r4 Athena reroute rows; "
              "each frozen parent order is preserved"
          ),
          "selection_independent_of_verifier_outcomes": True,
      },
  }


def expected_athena_recovery_manifest(
    original_path, reroute_path, sv_benchmarks
):
  inputs = (
      (
          Path(original_path).resolve(),
          FROZEN_ATHENA_MANIFEST_SHA256,
          "original Athena",
      ),
      (
          Path(reroute_path).resolve(),
          FROZEN_ATHENA_REROUTE_MANIFEST_SHA256,
          "r4 Athena reroute",
      ),
  )
  manifests = []
  for path, expected, name in inputs:
    if baseline.sha256_file(path) != expected:
      raise RuntimeError(f"{name} manifest hash is not frozen input")
    manifests.append(validate_manifest(path, sv_benchmarks))
  return athena_recovery_manifest(*manifests)


def command_athena_recovery(args):
  original_path = Path(args.athena_manifest).resolve()
  manifest = expected_athena_recovery_manifest(
      original_path, args.athena_reroute_manifest, args.sv_benchmarks
  )
  output = Path(args.output_dir).resolve()
  if output.exists() and any(output.iterdir()):
    raise RuntimeError(f"output directory must be absent or empty: {output}")
  output.mkdir(parents=True, exist_ok=True)
  for row in manifest.get("corpus_files", []):
    target = output / row["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original_path.parent / row["path"], target)
  manifest_path = output / "candidate-manifest-valkyrie.json"
  manifest_path.write_text(
      json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
  )
  manifest_sha256 = baseline.sha256_file(manifest_path)
  if manifest_sha256 != FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256:
    raise RuntimeError("Athena recovery manifest differs from frozen r5 output")
  print(
      json.dumps(
          {
              "manifest": manifest_path.name,
              "sha256": manifest_sha256,
              "task_count": manifest["task_count"],
          },
          sort_keys=True,
      )
  )


def command_validate_athena_recovery(args):
  expected = expected_athena_recovery_manifest(
      args.athena_manifest,
      args.athena_reroute_manifest,
      args.sv_benchmarks,
  )
  manifest_path = Path(args.manifest).resolve()
  actual = validate_manifest(manifest_path, args.sv_benchmarks)
  manifest_sha256 = baseline.sha256_file(manifest_path)
  if manifest_sha256 != FROZEN_ATHENA_RECOVERY_MANIFEST_SHA256:
    raise RuntimeError("Athena recovery manifest hash is not frozen r5 output")
  if actual != expected:
    raise RuntimeError(
        "Athena recovery manifest contains changed provenance, order, or rows"
    )
  print(
      json.dumps(
          {
              "sha256": manifest_sha256,
              "task_count": actual["task_count"],
              "valid": True,
          },
          sort_keys=True,
      )
  )


def validate_phase_a_partition(parent, phases):
  parent_rows = {row["task"]: row for row in parent["tasks"]}
  tasks = [
      row
      for role in FROZEN_PHASE_A_MANIFEST_SHA256
      for row in phases[role]["manifest"]["tasks"]
  ]
  names = [row["task"] for row in tasks]
  if len(names) != len(set(names)):
    raise RuntimeError("Phase-A manifests contain overlapping tasks")
  if set(names) != set(parent_rows):
    raise RuntimeError("Phase-A manifests do not partition the frozen parent")
  if any(parent_rows[row["task"]] != row for row in tasks):
    raise RuntimeError("Phase-A manifests contain changed task records")


def authenticate_phase_b_inputs(args):
  parent_path = Path(args.parent_manifest).resolve()
  if baseline.sha256_file(parent_path) != FROZEN_PARENT_MANIFEST_SHA256:
    raise RuntimeError("parent manifest hash is not the frozen 320-task input")
  parent = validate_manifest(parent_path, args.sv_benchmarks)
  parent_sha256 = baseline.sha256_file(parent_path)
  phases = {}
  role_by_hash = {
      digest: role for role, digest in FROZEN_PHASE_A_MANIFEST_SHA256.items()
  }
  for value in args.phase_a_manifest:
    path = Path(value).resolve()
    digest = baseline.sha256_file(path)
    role = role_by_hash.get(digest)
    if role is None or role in phases:
      raise RuntimeError("Phase-A manifest hash is not a distinct frozen input")
    manifest = validate_manifest(path, args.sv_benchmarks)
    derivation = manifest.get("derivation", {})
    if (
        derivation.get("host") != "valkyrie"
        or derivation.get("operation") != PHASE_A_OPERATION[role]
    ):
      raise RuntimeError(f"invalid Phase-A operation or host: {role}")
    phases[role] = {
        "manifest": manifest,
        "path": path,
        "sha256": digest,
        "role": role,
    }
  required_roles = set(FROZEN_PHASE_A_MANIFEST_SHA256)
  if not (
      required_roles
      == set(FROZEN_PHASE_A_RESULT_SHA256)
      == set(FROZEN_PHASE_A_SURVIVOR_SHA256)
      == set(FROZEN_PHASE_A_SURVIVOR_TASK_COUNT)
  ):
    raise RuntimeError("frozen Phase-A evidence pins have inconsistent roles")
  if set(phases) != required_roles:
    raise RuntimeError("Phase-A inputs must contain exactly three frozen manifests")
  validate_phase_a_partition(parent, phases)

  if len(args.phase_a_result) != len(required_roles):
    raise RuntimeError("Phase-A inputs must contain exactly three result files")
  results = {}
  result_role_by_hash = {
      digest: role for role, digest in FROZEN_PHASE_A_RESULT_SHA256.items()
  }
  for value in args.phase_a_result:
    path = Path(value).resolve()
    digest = baseline.sha256_file(path)
    role = result_role_by_hash.get(digest)
    if role is None or role in results:
      raise RuntimeError("Phase-A result hash is not a distinct frozen input")
    metadata = result_metadata(path, DISCOVERY_DISPLAY, "120 s")
    if metadata["host"] != "valkyrie":
      raise RuntimeError("Phase-A result hostname must be valkyrie")
    task_manifest = baseline.load_task_manifest(phases[role]["path"])
    validate_result_run_topology(path, task_manifest, args.sv_benchmarks)
    results[role] = {
        "path": path,
        "sha256": digest,
        **metadata,
    }
  for field in ("starttime", "benchmarkname"):
    if len({result[field] for result in results.values()}) != len(required_roles):
      raise RuntimeError(f"Phase-A results must have distinct {field} values")
  phase_by_hash = {item["sha256"]: role for role, item in phases.items()}
  survivor_role_by_hash = {
      digest: role for role, digest in FROZEN_PHASE_A_SURVIVOR_SHA256.items()
  }
  survivors = {}
  tasks = []
  for value in args.survivor_manifest:
    path = Path(value).resolve()
    digest = baseline.sha256_file(path)
    role = survivor_role_by_hash.get(digest)
    if role is None or role in survivors:
      raise RuntimeError("survivor manifest hash is not a distinct frozen input")
    manifest = validate_manifest(path, args.sv_benchmarks)
    derivation = manifest.get("derivation", {})
    if phase_by_hash.get(derivation.get("parent_manifest_sha256")) != role:
      raise RuntimeError("survivor has invalid Phase-A parent")
    phase = phases[role]
    result_hash = derivation.get("result_sha256")
    result = results[role]
    if result_hash != result["sha256"]:
      raise RuntimeError("survivor result hash does not match Phase A")
    expected_derivation = {
        "operation": "phase_a_analysis_survivors",
        "parent_manifest_sha256": phase["sha256"],
        "result_sha256": result_hash,
        "allowed_results": sorted(ANALYSIS_UNSOLVED),
        "phase_a_host": "valkyrie",
        "selection_independent_of_augmented_outcomes": True,
    }
    if derivation != expected_derivation:
      raise RuntimeError("survivor provenance is not frozen Phase A")
    if manifest["task_count"] != FROZEN_PHASE_A_SURVIVOR_TASK_COUNT[role]:
      raise RuntimeError("survivor task count is not the frozen Phase-A count")
    runs = baseline.parse_result_rows(
        result["path"],
        baseline.load_task_manifest(phase["path"]),
        hard_threshold=200,
    )
    if any(
        row["cpu_time_seconds"] is None or row["wall_time_seconds"] is None
        for row in runs
    ):
      raise RuntimeError("Phase-A result lacks parseable CPU or wall metrics")
    selected = {
        row["task"]
        for row in runs
        if classify_screen_result(row) == "analysis_survivor"
    }
    expected = manifest_subset(phase["manifest"], selected, expected_derivation)
    if manifest != expected:
      raise RuntimeError("survivor rows do not match recomputed Phase-A results")
    survivors[role] = {
        "manifest": manifest,
        "sha256": digest,
        "result_sha256": result_hash,
    }
    tasks.extend(row["task"] for row in manifest["tasks"])
  if set(survivors) != required_roles:
    raise RuntimeError("survivors and results must cover exactly three Phase-A inputs")
  if len(tasks) != len(set(tasks)):
    raise RuntimeError("Phase-A survivor sets contain duplicate tasks")
  inputs = [
      {
          "role": role,
          "phase_a_manifest_sha256": phases[role]["sha256"],
          "phase_a_result_sha256": survivors[role]["result_sha256"],
          "survivor_manifest_sha256": survivors[role]["sha256"],
          "survivor_task_count": survivors[role]["manifest"]["task_count"],
      }
      for role in FROZEN_PHASE_A_MANIFEST_SHA256
  ]
  merged = manifest_subset(
      parent,
      tasks,
      {
          "operation": "merge_phase_a_survivors_single_host",
          "parent_manifest_sha256": parent_sha256,
          "host": "valkyrie",
          "phase_a_inputs": inputs,
          "selection_independent_of_augmented_outcomes": True,
      },
  )
  return parent, parent_sha256, merged


def authenticate_formal_manifest(args):
  if hasattr(args, "phase_a_output"):
    phase_a_manifest, host = authenticate_cap16_phase_a_output(
        args.phase_a_output, args.sv_benchmarks
    )
    manifest_path = Path(args.manifest).resolve()
    expected_path = (
        Path(args.phase_a_output).resolve()
        / "summary/candidate-manifest-analysis-survivors.json"
    )
    if manifest_path != expected_path:
      raise RuntimeError(
          "cap-16 formal manifest must be the authenticated Phase-A survivor"
      )
    manifest = validate_manifest(manifest_path, args.sv_benchmarks)
    if manifest != phase_a_manifest:
      raise RuntimeError(
          "cap-16 formal manifest differs from authenticated Phase-A survivors"
      )
    return manifest, host
  _, _, merged = authenticate_phase_b_inputs(args)
  manifest_path = Path(args.manifest).resolve()
  if baseline.sha256_file(manifest_path) != FROZEN_FORMAL_MANIFEST_SHA256:
    raise RuntimeError("formal manifest hash is not the frozen Phase-B input")
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  if manifest != merged:
    raise RuntimeError("formal manifest does not match authenticated Valkyrie merge")
  return manifest, "valkyrie"


def validate_artifact_manifest_index(artifact):
  if (
      not isinstance(artifact, dict)
      or set(artifact)
      != {"root", "file_count", "aggregate_sha256", "files"}
      or not isinstance(artifact["root"], str)
      or not isinstance(artifact["files"], list)
  ):
    raise RuntimeError("artifact manifest topology is invalid")
  entries = []
  aggregate = hashlib.sha256()
  for entry in artifact["files"]:
    if (
        not isinstance(entry, dict)
        or set(entry) != {"path", "size_bytes", "sha256"}
        or not isinstance(entry["path"], str)
        or Path(entry["path"]).is_absolute()
        or ".." in Path(entry["path"]).parts
        or not isinstance(entry["size_bytes"], int)
        or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
    ):
      raise RuntimeError("artifact manifest entry is invalid")
    entries.append(entry["path"])
    aggregate.update(entry["path"].encode("utf-8"))
    aggregate.update(b"\0")
    aggregate.update(bytes.fromhex(entry["sha256"]))
  if entries != sorted(entries) or len(entries) != len(set(entries)):
    raise RuntimeError("artifact manifest paths are not unique and sorted")
  if (
      artifact["file_count"] != len(entries)
      or artifact["aggregate_sha256"] != aggregate.hexdigest()
  ):
    raise RuntimeError("artifact manifest aggregate is invalid")
  return {entry["path"]: entry for entry in artifact["files"]}


def validate_artifact_manifest(
    root, artifact_path, ignored, expected_root=None
):
  root = Path(root).resolve()
  artifact_path = Path(artifact_path).resolve()
  artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
  entries = validate_artifact_manifest_index(artifact)
  if artifact["root"] != (
      str(root) if expected_root is None else expected_root
  ):
    raise RuntimeError("artifact manifest root is invalid")
  for relative, entry in entries.items():
    path = root / relative
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != entry["size_bytes"]
        or baseline.sha256_file(path) != entry["sha256"]
    ):
      raise RuntimeError(f"artifact manifest mismatch: {relative}")
  ignored = {Path(path).as_posix() for path in ignored}
  actual = []
  for path in root.rglob("*"):
    mode = path.lstat().st_mode
    if stat.S_ISDIR(mode):
      continue
    relative = path.relative_to(root).as_posix()
    if path == artifact_path or relative in ignored:
      continue
    if not stat.S_ISREG(mode):
      raise RuntimeError(f"unsupported artifact node: {path}")
    actual.append(relative)
  if list(entries) != sorted(actual):
    raise RuntimeError("artifact manifest file set is incomplete")
  return artifact


def validate_cap16_phase_a_structure(
    phase_a_output, sv_benchmarks, portable
):
  declared = Path(phase_a_output)
  root = declared.resolve()
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != root
      or not root.is_dir()
  ):
    raise RuntimeError("cap-16 Phase-A output must be a regular directory")
  complete = root / "summary/.complete"
  if (
      complete.is_symlink()
      or not complete.is_file()
      or complete.read_text(encoding="utf-8") != "complete\n"
  ):
    raise RuntimeError("cap-16 Phase-A output is not complete")
  manifest_path = root / "input/candidate-manifest-athena.json"
  if baseline.sha256_file(manifest_path) != FROZEN_CAP16_ATHENA_MANIFEST_SHA256:
    raise RuntimeError("cap-16 Phase-A manifest hash is not frozen")
  manifest = validate_manifest(manifest_path, sv_benchmarks)
  derivation = manifest.get("derivation", {})
  if (
      manifest["task_count"] != FROZEN_CAP16_PHASE_A_TASK_COUNT
      or derivation.get("operation") != "deterministic_stratified_shard"
      or derivation.get("parent_manifest_sha256")
      != FROZEN_CAP16_PARENT_MANIFEST_SHA256
      or derivation.get("hosts") != ["athena"]
      or derivation.get("host") != "athena"
      or derivation.get("selection_independent_of_verifier_outcomes") is not True
  ):
    raise RuntimeError("cap-16 Phase-A manifest provenance is invalid")
  definition = root / "generated/hard-case-candidates.xml"
  validate_screen_definition(
      definition, manifest_path, manifest, sv_benchmarks
  )
  rows = baseline.load_task_manifest(manifest_path)
  plan = load_screen_plan(
      root / "screen-plan.json",
      rows,
      manifest_path,
      "athena",
      sv_benchmarks,
      definition,
  )
  row_provenance_content = json.dumps({
      "schema_version": "hard-case-screen-row-provenance-v1",
      "screen_plan_sha256": plan["plan_sha256"],
      "primary_result_sha256": plan["primary_sha256"],
      "replacement_result_sha256": plan["replacement_sha256"],
      "rows": plan["row_sources"],
  }, indent=2) + "\n"
  row_provenance_path = root / "summary/row-provenance.json"
  if row_provenance_path.read_text(encoding="utf-8") != row_provenance_content:
    raise RuntimeError("cap-16 Phase-A row provenance is invalid")
  accepted = [plan["rows"][task] for task in rows]
  if any(
      run["cpu_time_seconds"] is None or run["wall_time_seconds"] is None
      for run in accepted
  ):
    raise RuntimeError("cap-16 Phase-A result lacks CPU or wall metrics")
  survivor_tasks = [
      run["task"]
      for run in accepted
      if classify_screen_result(run) == "analysis_survivor"
  ]
  provenance = {
      "screen_plan_sha256": plan["plan_sha256"],
      "result_sha256": [
          plan["primary_sha256"],
          *plan["replacement_sha256"],
      ],
      "row_provenance_sha256": hashlib.sha256(
          row_provenance_content.encode("utf-8")
      ).hexdigest(),
  }
  expected = manifest_subset(
      manifest,
      survivor_tasks,
      {
          "operation": "phase_a_analysis_survivors",
          "parent_manifest_sha256": FROZEN_CAP16_ATHENA_MANIFEST_SHA256,
          **provenance,
          "allowed_results": sorted(ANALYSIS_UNSOLVED),
          "phase_a_host": "athena",
          "selection_independent_of_augmented_outcomes": True,
      },
  )
  survivor_path = (
      root / "summary/candidate-manifest-analysis-survivors.json"
  )
  survivor = validate_manifest(survivor_path, sv_benchmarks)
  if survivor != expected:
    raise RuntimeError(
        "cap-16 Phase-A survivor differs from recomputed screen plan"
    )
  counts = collections.Counter(
      classify_screen_result(run) for run in accepted
  )
  expected_summary = {
      "task_count": len(accepted),
      "phase_a_host": "athena",
      "classifications": dict(sorted(counts.items())),
      **provenance,
      "survivor_manifest_sha256": baseline.sha256_file(survivor_path),
  }
  summary = json.loads(
      (root / "summary/summary.json").read_text(encoding="utf-8")
  )
  if summary != expected_summary:
    raise RuntimeError("cap-16 Phase-A summary is invalid")
  artifact = validate_artifact_manifest(
      root,
      root / "provenance/artifact-manifest.json",
      {"summary/.complete"},
      expected_root="." if portable else None,
  )
  return survivor, "athena", artifact


def authenticate_cap16_phase_a_output(phase_a_output, sv_benchmarks):
  survivor, host, artifact = validate_cap16_phase_a_structure(
      phase_a_output, sv_benchmarks, portable=True
  )
  frozen = FROZEN_CAP16_PHASE_A_PACKAGE_AGGREGATE_SHA256
  if not re.fullmatch(r"[0-9a-f]{64}", frozen):
    raise RuntimeError(
        "cap-16 Phase-A package aggregate is pending and formal execution "
        "is disabled"
    )
  if artifact["aggregate_sha256"] != frozen:
    raise RuntimeError("cap-16 Phase-A package aggregate is not frozen")
  return survivor, host


def command_package_cap16_phase_a(args):
  source = Path(args.phase_a_output)
  validate_cap16_phase_a_structure(
      source, args.sv_benchmarks, portable=False
  )
  source = source.resolve()
  output = Path(args.output_dir).resolve()
  if output == source or source in output.parents or output in source.parents:
    raise RuntimeError("cap-16 package output overlaps its Phase-A source")
  require_absent_or_empty_output(output)
  shutil.copytree(source, output, dirs_exist_ok=True)
  (output / "summary/.complete").unlink()
  (output / "provenance/artifact-manifest.json").unlink()
  manifest_path = output / "input/candidate-manifest-athena.json"
  manifest_rows = baseline.load_task_manifest(manifest_path)
  sv_benchmarks = Path(args.sv_benchmarks).resolve()
  for definition in sorted(output.glob("generated/**/hard-case-candidates.xml")):
    root = ET.parse(definition).getroot()
    for node in root.findall(".//includesfile"):
      value = Path(node.text)
      if not value.name.startswith("hard-case-candidates-"):
        raise RuntimeError("cap-16 package contains an unknown task set")
      task_set = definition.parent / value.name
      portable_tasks = []
      for task in task_set.read_text(encoding="utf-8").splitlines():
        path = Path(task).resolve()
        try:
          portable_tasks.append(path.relative_to(sv_benchmarks).as_posix())
        except ValueError as error:
          raise RuntimeError(
              "cap-16 package contains a non-SV-Benchmarks task"
          ) from error
      task_set.write_text(
          "\n".join(portable_tasks) + "\n", encoding="utf-8"
      )
      node.text = value.name
    for node in root.findall(".//propertyfile"):
      node.text = "c/properties/unreach-call.prp"
    write_xml(root, definition)

  plan_path = output / "screen-plan.json"
  plan = json.loads(plan_path.read_text(encoding="utf-8"))
  result_entries = [plan["primary"], *plan["replacements"]]
  for entry in result_entries:
    result_path = output / entry["path"]
    with baseline.open_result(result_path) as source_file:
      result = ET.parse(source_file)
    for run in result.getroot().findall("run"):
      task = baseline.match_result_task(run.get("name", ""), manifest_rows)
      row = manifest_rows[task]
      if row["source"] != "sv-benchmarks":
        raise RuntimeError(
            "cap-16 package contains a non-SV-Benchmarks result row"
        )
      run.set("name", row["task_path"])
      run.set("files", f"[{', '.join(row['source_paths'])}]")
      run.set("propertyFile", "c/properties/unreach-call.prp")
    if result_path.suffix == ".bz2":
      content = ET.tostring(result.getroot(), encoding="unicode")
      result_path.write_bytes(bz2.compress(content.encode("utf-8")))
    else:
      result.write(result_path, encoding="unicode")

  plan["primary"]["sha256"] = baseline.sha256_file(
      output / plan["primary"]["path"]
  )
  if plan["taint"] is not None:
    taint_path = output / plan["taint"]["path"]
    taint = json.loads(taint_path.read_text(encoding="utf-8"))
    taint["primary_result_sha256"] = plan["primary"]["sha256"]
    taint_path.write_text(
        json.dumps(taint, indent=2) + "\n", encoding="utf-8"
    )
    plan["taint"]["sha256"] = baseline.sha256_file(taint_path)
  for entry in plan["replacements"]:
    result_path = output / entry["path"]
    definition = plan_path.parent / entry["definition_path"]
    taint_path = output / entry["taint_path"]
    entry["sha256"] = baseline.sha256_file(result_path)
    entry["definition_sha256"] = baseline.sha256_file(definition)
    taint = json.loads(taint_path.read_text(encoding="utf-8"))
    taint["primary_result_sha256"] = entry["sha256"]
    taint_path.write_text(
        json.dumps(taint, indent=2) + "\n", encoding="utf-8"
    )
    entry["taint_sha256"] = baseline.sha256_file(taint_path)
  plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
  summary = output / "summary"
  shutil.rmtree(summary)
  command_screen_summary_plan(argparse.Namespace(
      manifest=str(output / "input/candidate-manifest-athena.json"),
      benchmark_definition=str(output / "generated/hard-case-candidates.xml"),
      screen_plan=str(plan_path),
      sv_benchmarks=args.sv_benchmarks,
      phase_a_host="athena",
      output_dir=str(summary),
  ))
  artifact = baseline.write_artifact_manifest(
      output,
      output / "provenance/artifact-manifest.json",
      root_label=".",
  )
  (summary / ".complete").write_text("complete\n", encoding="utf-8")
  validate_cap16_phase_a_structure(
      output, args.sv_benchmarks, portable=True
  )
  print(json.dumps({
      "aggregate_sha256": artifact["aggregate_sha256"],
      "output": str(output),
      "task_count": json.loads(
          (output / "input/candidate-manifest-athena.json").read_text(
              encoding="utf-8"
          )
      )["task_count"],
  }, sort_keys=True))


def command_validate_cap16_phase_a(args):
  manifest, host = authenticate_cap16_phase_a_output(
      args.phase_a_output, args.sv_benchmarks
  )
  print(json.dumps({
      "host": host,
      "manifest_sha256": baseline.sha256_file(
          Path(args.phase_a_output)
          / "summary/candidate-manifest-analysis-survivors.json"
      ),
      "task_count": manifest["task_count"],
      "valid": True,
  }, sort_keys=True))


def copy_declared_corpus_files(manifest_path, manifest, output):
  source_root = Path(manifest_path).resolve().parent
  copied = set()
  for row in manifest.get("corpus_files", []):
    relative = Path(row["path"])
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() in copied
    ):
      raise RuntimeError(f"invalid declared corpus path: {row['path']}")
    source = (source_root / relative).resolve()
    try:
      source.relative_to(source_root)
    except ValueError as error:
      raise RuntimeError(
          f"declared corpus path escapes source: {row['path']}"
      ) from error
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    copied.add(relative.as_posix())


def write_phase_b_artifact_manifest(output):
  path = output / "artifact-manifest.json"
  artifact = baseline.write_artifact_manifest(output, path, root_label=".")
  return artifact, baseline.sha256_file(path)


def command_merge_survivors(args):
  _, _, merged = authenticate_phase_b_inputs(args)
  output = Path(args.output_dir).resolve()
  require_absent_or_empty_output(output)
  output.mkdir(parents=True, exist_ok=True)
  path = output / "candidate-manifest-valkyrie-formal.json"
  path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
  manifest_sha256 = baseline.sha256_file(path)
  if manifest_sha256 != FROZEN_FORMAL_MANIFEST_SHA256:
    raise RuntimeError("merged formal manifest differs from frozen Phase-B output")
  copy_declared_corpus_files(args.parent_manifest, merged, output)
  validate_manifest(path, args.sv_benchmarks)
  artifact, artifact_sha256 = write_phase_b_artifact_manifest(output)
  print(
      json.dumps(
          {
              "aggregate_sha256": artifact["aggregate_sha256"],
              "artifact_manifest_sha256": artifact_sha256,
              "host": "valkyrie",
              "manifest_sha256": manifest_sha256,
              "task_count": merged["task_count"],
          },
          sort_keys=True,
      )
  )


def validate_manifest(manifest_path, sv_benchmarks):
  manifest_path = Path(manifest_path).resolve()
  manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
  if manifest.get("task_count") != len(manifest.get("tasks", [])):
    raise RuntimeError("candidate manifest task count is invalid")
  tasks = [row["task"] for row in manifest["tasks"]]
  if len(tasks) != len(set(tasks)):
    raise RuntimeError("candidate manifest contains duplicate tasks")
  for row in manifest.get("corpus_files", []):
    path = manifest_path.parent / row["path"]
    if not path.is_file() or baseline.sha256_file(path) != row["sha256"]:
      raise RuntimeError(f"candidate hash mismatch: {path}")
  for row in manifest["tasks"]:
    root = (
        Path(sv_benchmarks).resolve()
        if row["source"] == "sv-benchmarks"
        else manifest_path.parent
    )
    paths = [root / row["task_path"], *(root / path for path in row["source_paths"])]
    hashes = [row["task_sha256"], *row["source_sha256"]]
    for path, expected in zip(paths, hashes, strict=True):
      if not path.is_file() or baseline.sha256_file(path) != expected:
        raise RuntimeError(f"candidate hash mismatch: {path}")
  return manifest


def command_validate(args):
  manifest = validate_manifest(args.manifest, args.sv_benchmarks)
  print(json.dumps({"task_count": manifest["task_count"], "valid": True}))


def git_blob(repo, path):
  return subprocess.check_output(
      ["git", "-C", str(repo), "show", f"HEAD:{path}"]
  )


def official_license_files(repo):
  paths = subprocess.check_output(
      ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD"],
      text=True,
  ).splitlines()
  result = collections.defaultdict(list)
  for path in paths:
    if Path(path).name.lower().startswith(("license", "copying", "copyright")):
      result[Path(path).parent.as_posix()].append(path)
  return result


def official_license_evidence(repo, source_path, license_files):
  content = git_blob(repo, source_path)
  text = content.decode("utf-8", errors="replace")
  identifiers = []
  statements = []
  for line in text.splitlines():
    if "SPDX-License-Identifier:" in line:
      identifiers.append(
          line.partition("SPDX-License-Identifier:")[2].strip().rstrip("*/").strip()
      )
    match = re.search(r"Licensed under the ([^*]+)", line, re.IGNORECASE)
    if match:
      statements.append(match.group(1).strip())
  if identifiers or statements:
    return [
        {
            "kind": "source_header",
            "path": source_path,
            "sha256": hashlib.sha256(content).hexdigest(),
            "identifiers": sorted(set(identifiers)),
            "statements": sorted(set(statements)),
        }
    ]
  evidence = []
  for path in license_files.get(Path(source_path).parent.as_posix(), []):
    blob = git_blob(repo, path)
    evidence.append(
        {
            "kind": "directory_license_file",
            "path": path,
            "sha256": hashlib.sha256(blob).hexdigest(),
        }
    )
  return evidence


def command_license_audit(args):
  manifest_path = Path(args.manifest).resolve()
  validate_manifest(manifest_path, args.sv_benchmarks)
  full_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
  sv_benchmarks = Path(args.sv_benchmarks).resolve()
  external_root = Path(args.external_root).resolve()
  if git_head(sv_benchmarks) != full_manifest["repositories"]["sv-benchmarks"]:
    raise RuntimeError("sv-benchmarks revision does not match candidate manifest")
  for source in SOURCE_LICENSE_FILES:
    if git_head(external_root / source) != full_manifest["repositories"][source]:
      raise RuntimeError(f"{source} revision does not match candidate manifest")

  official_files = official_license_files(sv_benchmarks)
  included = []
  audit_rows = []
  for task in full_manifest["tasks"]:
    evidence = []
    if task["source"] == "sv-benchmarks":
      missing = []
      for source_path in task["source_paths"]:
        source_evidence = official_license_evidence(
            sv_benchmarks, source_path, official_files
        )
        if source_evidence:
          evidence.extend(source_evidence)
        else:
          missing.append(source_path)
    else:
      license_path = SOURCE_LICENSE_FILES[task["source"]]
      license_content = git_blob(external_root / task["source"], license_path)
      evidence = [
          {
              "kind": "repository_license_file",
              "repository": SOURCE_URLS[task["source"]],
              "revision": full_manifest["repositories"][task["source"]],
              "path": license_path,
              "sha256": hashlib.sha256(license_content).hexdigest(),
          }
      ]
      missing = []
    status = "included" if not missing else "license_unresolved"
    audit_rows.append(
        {
            "task": task["task"],
            "source": task["source"],
            "expected_verdict": task["expected_verdict"],
            "status": status,
            "missing_source_paths": ";".join(missing),
            "license_evidence": json.dumps(evidence, sort_keys=True),
        }
    )
    if status == "included":
      included.append(
          {
              **task,
              "license": (
                  task["license"]
                  if task["source"] != "sv-benchmarks"
                  else "see license_evidence"
              ),
              "license_evidence": evidence,
          }
      )

  output = Path(args.output_dir).resolve()
  output.mkdir(parents=True, exist_ok=True)
  if output != manifest_path.parent:
    shutil.copytree(manifest_path.parent / "corpus", output / "corpus")
    shutil.copy2(manifest_path, output / "candidate-manifest.json")
  excluded = [row for row in audit_rows if row["status"] != "included"]
  audited_manifest = {
      **full_manifest,
      "schema_version": "hard-case-candidate-v1-license-audited",
      "task_count": len(included),
      "license_audit": {
          "input_manifest_sha256": baseline.sha256_file(manifest_path),
          "selection_independent_of_verifier_outcomes": True,
          "included_task_count": len(included),
          "excluded_task_count": len(excluded),
          "excluded_tasks": [row["task"] for row in excluded],
          "repositories": {
              "sv-benchmarks": {
                  "url": SOURCE_URLS["sv-benchmarks"],
                  "revision": full_manifest["repositories"]["sv-benchmarks"],
              },
              **{
                  source: {
                      "url": SOURCE_URLS[source],
                      "revision": full_manifest["repositories"][source],
                      "license_file": SOURCE_LICENSE_FILES[source],
                  }
                  for source in SOURCE_LICENSE_FILES
              },
          },
      },
      "tasks": included,
  }
  (output / "candidate-manifest-license-audited.json").write_text(
      json.dumps(audited_manifest, indent=2) + "\n", encoding="utf-8"
  )
  fieldnames = list(audit_rows[0])
  for filename, rows in (
      ("license-audit.csv", audit_rows),
      ("license-quarantine.csv", excluded),
  ):
    with (output / filename).open("w", newline="", encoding="utf-8") as target:
      writer = csv.DictWriter(target, fieldnames=fieldnames)
      writer.writeheader()
      writer.writerows(rows)
  print(
      json.dumps(
          {
              "included": len(included),
              "license_unresolved": len(excluded),
              "manifest": str(output / "candidate-manifest-license-audited.json"),
          }
      )
  )


def classify_probe_events(events):
  if any(event.get("counterexample_visits_loop_head") is True for event in events):
    return "cegar_eligible"
  return "hook_reached_without_loop_head" if events else "structurally_unreachable"


def validate_probe_events(events):
  if not isinstance(events, list):
    raise RuntimeError("probe telemetry is not an event list")
  expected_roles = ("invariant", "counterexample", "refinement")
  for refinement, event in enumerate(events, start=1):
    if (
        not isinstance(event, dict)
        or set(event)
        != {
            "schema_version",
            "refinement",
            "counterexample_visits_loop_head",
            "provider_calls",
            "activated_candidates",
            "rejected_candidates",
        }
        or event["schema_version"] != "vguide-telemetry-v1"
        or type(event["refinement"]) is not int
        or event["refinement"] != refinement
        or not isinstance(event["counterexample_visits_loop_head"], bool)
        or event["activated_candidates"] != []
        or type(event["rejected_candidates"]) is not int
        or event["rejected_candidates"] != 0
        or not isinstance(event["provider_calls"], list)
        or len(event["provider_calls"]) != len(expected_roles)
    ):
      raise RuntimeError("probe telemetry event topology is invalid")
    for role, call in zip(
        expected_roles, event["provider_calls"], strict=True
    ):
      if (
          not isinstance(call, dict)
          or set(call) != {"agent_role", "model", "response_sha256"}
          or call["agent_role"] != role
          or call["model"] != EMPTY_PROVIDER_MODEL
          or call["response_sha256"] != EMPTY_PROVIDER_RESPONSE_SHA256
      ):
        raise RuntimeError("probe telemetry provider call is not deterministic EMPTY")
  return classify_probe_events(events)


def command_probe_summary(args):
  manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
  details = {row["task"]: row for row in manifest["tasks"]}
  with Path(args.hard_portfolio).open(newline="", encoding="utf-8") as source:
    hard_rows = list(csv.DictReader(source))
  result_files = Path(args.result_files)
  telemetry_files = list(result_files.rglob("vguide-telemetry.json"))
  rows = []
  for hard in hard_rows:
    detail = details[hard["task"]]
    task_basename = Path(detail["task_path"]).name
    matches = [
        path for path in telemetry_files if path.parent.parent.name == task_basename
    ]
    if len(matches) > 1:
      raise RuntimeError(f"multiple telemetry files for {hard['task']}")
    if not matches:
      classification = "infrastructure_failure"
      rounds = None
      telemetry_sha256 = ""
    else:
      events = json.loads(matches[0].read_text(encoding="utf-8"))
      classification = validate_probe_events(events)
      rounds = len(events)
      telemetry_sha256 = baseline.sha256_file(matches[0])
    rows.append(
        {
            **hard,
            "probe_classification": classification,
            "augmented_refinement_rounds": rounds,
            "telemetry_sha256": telemetry_sha256,
        }
    )
  output = Path(args.output_dir)
  output.mkdir(parents=True, exist_ok=True)
  fieldnames = list(rows[0]) if rows else []
  for filename, subset in (
      ("cegar-eligibility.csv", rows),
      (
          "cegar-eligible.csv",
          [row for row in rows if row["probe_classification"] == "cegar_eligible"],
      ),
      (
          "structurally-unreachable.csv",
          [
              row
              for row in rows
              if row["probe_classification"] == "structurally_unreachable"
          ],
      ),
  ):
    with (output / filename).open("w", newline="", encoding="utf-8") as target:
      writer = csv.DictWriter(target, fieldnames=fieldnames)
      writer.writeheader()
      writer.writerows(subset)
  counts = collections.Counter(row["probe_classification"] for row in rows)
  (output / "cegar-eligibility-summary.json").write_text(
      json.dumps(
          {
              "task_count": len(rows),
              "classifications": dict(sorted(counts.items())),
          },
          indent=2,
      )
      + "\n",
      encoding="utf-8",
  )


def probe_result_telemetry(result_path, manifest):
  result_path = Path(result_path).resolve()
  result_tasks = result_task_names(result_path, manifest)
  basenames = {
      task: Path(manifest[task]["task_path"]).name for task in result_tasks
  }
  if len(set(basenames.values())) != len(basenames):
    raise RuntimeError("probe result tasks have ambiguous task basenames")
  files_dirs = [
      path for path in result_path.parent.iterdir()
      if path.name.endswith(".files")
  ]
  actual = set(result_path.parent.rglob("vguide-telemetry.json"))
  if len(files_dirs) > 1:
    raise RuntimeError("probe result has multiple retrieved-result directories")
  if not files_dirs:
    if actual:
      raise RuntimeError(
          f"probe result contains misplaced telemetry: {sorted(map(str, actual))}"
      )
    return dict.fromkeys(result_tasks)
  if files_dirs[0].is_symlink() or not files_dirs[0].is_dir():
    raise RuntimeError("probe retrieved-result directory is not regular")
  expected = {
      task: (
          files_dirs[0]
          / "cegar-eligibility"
          / basename
          / "output/vguide-telemetry.json"
      )
      for task, basename in basenames.items()
  }
  unknown = actual - set(expected.values())
  if unknown:
    raise RuntimeError(
        f"probe result contains unknown telemetry: {sorted(map(str, unknown))}"
    )
  return expected


def strict_probe_summary_rows(args, cohort):
  profile = strict_probe_profile(cohort)
  validate_input = (
      validate_cap8_probe_input
      if cohort == "cap8"
      else validate_cap16_probe_input
  )
  _, manifest_path, manifest_data, hard_rows, identity = (
      validate_input(args.probe_input, args.sv_benchmarks)
  )
  manifest = baseline.load_task_manifest(manifest_path)
  validate_probe_definition(
      args.benchmark_definition,
      manifest_path,
      manifest_data,
      args.sv_benchmarks,
  )
  plan_path = Path(args.probe_plan).resolve()
  plan = load_screen_plan(
      plan_path,
      manifest,
      manifest_path,
      profile["host"],
      args.sv_benchmarks,
      args.benchmark_definition,
      plan_schema=profile["plan_schema"],
      repetition=1,
      display=PROBE_DISPLAY,
      time_limit="900 s",
      taint_schema=profile["taint_schema"],
      definition_validator=validate_probe_definition,
      hard_threshold=200,
  )
  source_by_task = {row["task"]: row for row in plan["row_sources"]}
  row_by_task = {row["task"]: row for row in plan["rows"].values()}
  telemetry_by_result = {}
  rows = []
  for hard in hard_rows:
    task = hard["task"]
    source = source_by_task[task]
    result = declared_plan_file(
        plan_path.parent,
        {
            "path": source["result_path"],
            "sha256": source["result_sha256"],
        },
        f"probe result for {task}",
    )
    if result not in telemetry_by_result:
      telemetry_by_result[result] = probe_result_telemetry(result, manifest)
    telemetry = telemetry_by_result[result][task]
    result_row = row_by_task[task]
    explicit_failure = result_row["classification"] in {
        "out_of_memory",
        "verifier_or_resource_error",
        "infrastructure_or_manifest_failure",
    }
    if telemetry is not None and telemetry.is_symlink():
      raise RuntimeError(f"probe telemetry is a symlink for {task}")
    if telemetry is not None and telemetry.exists() and not telemetry.is_file():
      raise RuntimeError(f"probe telemetry is not a regular file for {task}")
    if telemetry is not None and telemetry.is_file():
      events = json.loads(telemetry.read_text(encoding="utf-8"))
      event_classification = validate_probe_events(events)
      rounds = len(events)
      telemetry_sha256 = baseline.sha256_file(telemetry)
      if explicit_failure:
        classification = "infrastructure_failure"
        infrastructure_reason = (
            f"result failure; status={result_row['status']}; "
            f"category={result_row['category']}"
        )
      else:
        classification = (
            "no_event"
            if event_classification == "structurally_unreachable"
            else event_classification
        )
        infrastructure_reason = ""
    else:
      if not explicit_failure:
        raise RuntimeError(f"probe telemetry is unexpectedly missing for {task}")
      classification = "infrastructure_failure"
      rounds = ""
      telemetry_sha256 = ""
      infrastructure_reason = (
          f"missing telemetry; status={result_row['status']}; "
          f"category={result_row['category']}"
      )
    rows.append({
        **hard,
        "probe_classification": classification,
        "probe_refinement_rounds": rounds,
        "telemetry_sha256": telemetry_sha256,
        "probe_result_sha256": source["result_sha256"],
        "probe_result_source": source["source"],
        "infrastructure_reason": infrastructure_reason,
    })
  if {row["task"] for row in rows} != set(manifest):
    raise RuntimeError("probe summary does not cover exactly the authenticated manifest")
  return rows, plan, identity


def cap16_probe_summary_rows(args):
  return strict_probe_summary_rows(args, "cap16")


def cap8_probe_summary_rows(args):
  return strict_probe_summary_rows(args, "cap8")


def write_strict_probe_summary(args, cohort, rows_provider=None):
  profile = strict_probe_profile(cohort)
  require_absent_or_empty_output(args.output_dir)
  if rows_provider is None:
    rows_provider = lambda value: strict_probe_summary_rows(value, cohort)
  rows, plan, identity = rows_provider(args)
  output = Path(args.output_dir).resolve()
  output.mkdir(parents=True, exist_ok=True)
  fieldnames = list(rows[0])
  for filename, classification in (
      ("cegar-eligibility.csv", None),
      *STRICT_PROBE_STRATA,
  ):
    with (output / filename).open(
        "w", newline="", encoding="utf-8"
    ) as target:
      writer = csv.DictWriter(target, fieldnames=fieldnames)
      writer.writeheader()
      writer.writerows(
          rows
          if classification is None
          else (
              row for row in rows
              if row["probe_classification"] == classification
          )
      )
  row_provenance = {
      "schema_version": profile["row_provenance_schema"],
      "probe_plan_sha256": plan["plan_sha256"],
      "primary_result_sha256": plan["primary_sha256"],
      "replacement_result_sha256": plan["replacement_sha256"],
      "rows": plan["row_sources"],
  }
  provenance_path = output / "row-provenance.json"
  provenance_path.write_text(
      json.dumps(row_provenance, indent=2) + "\n", encoding="utf-8"
  )
  counts = collections.Counter(row["probe_classification"] for row in rows)
  summary = {
      "schema_version": profile["summary_schema"],
      "task_count": len(rows),
      "classifications": dict(sorted(counts.items())),
      "host": profile["host"],
      "provider": "EMPTY",
      "activated_candidate_count": 0,
      "formal_artifact_aggregate_sha256": identity[
          "formal_artifact_aggregate_sha256"
      ],
      "probe_input_manifest_sha256": identity["probe_manifest_sha256"],
      "probe_plan_sha256": plan["plan_sha256"],
      "row_provenance_sha256": baseline.sha256_file(provenance_path),
  }
  (output / "summary.json").write_text(
      json.dumps(summary, indent=2) + "\n", encoding="utf-8"
  )
  return summary


def write_cap8_probe_summary(args):
  return write_strict_probe_summary(args, "cap8", cap8_probe_summary_rows)


def write_cap16_probe_summary(args):
  return write_strict_probe_summary(
      args, "cap16", cap16_probe_summary_rows
  )


def command_cap8_probe_summary(args):
  print(json.dumps(write_cap8_probe_summary(args), sort_keys=True))


def command_cap16_probe_summary(args):
  print(json.dumps(write_cap16_probe_summary(args), sort_keys=True))


def classify_screen_result(row):
  if row["category"] == "wrong":
    return "wrong_quarantine"
  if (
      row["classification"] == "infrastructure_or_manifest_failure"
      or (
          row["category"] == "correct"
          and row["cpu_time_seconds"] is None
      )
  ):
    return "infrastructure_failure"
  if row["category"] == "correct":
    return "correct_fast"
  if is_analysis_unsolved(row):
    return "analysis_survivor"
  return "verifier_failure_quarantine"


def validate_phase_a_host(result_path, requested_host, manifest_host):
  with baseline.open_result(Path(result_path)) as source:
    root = ET.parse(source).getroot()
  systeminfo = root.findall("systeminfo")
  if len(systeminfo) != 1 or not systeminfo[0].get("hostname"):
    raise RuntimeError("screen result must contain exactly one systeminfo hostname")
  result_host = systeminfo[0].get("hostname")
  if (
      requested_host not in DISCOVERY_HOSTS
      or manifest_host != requested_host
      or result_host != requested_host
  ):
    raise RuntimeError("Phase-A host does not match result and manifest provenance")
  return requested_host


def command_screen_summary(args):
  manifest_path = Path(args.manifest).resolve()
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  phase_a_host = validate_phase_a_host(
      args.result,
      args.phase_a_host,
      manifest.get("derivation", {}).get("host"),
  )
  parsed_manifest = baseline.load_task_manifest(manifest_path)
  runs = baseline.parse_result_rows(args.result, parsed_manifest, hard_threshold=200)
  write_screen_summary(
      args,
      manifest_path,
      manifest,
      phase_a_host,
      runs,
      {
          "result_sha256": baseline.sha256_file(Path(args.result)),
      },
  )


def write_screen_summary(
    args,
    manifest_path,
    manifest,
    phase_a_host,
    runs,
    provenance,
):
  missing_metrics = [
      run["task"]
      for run in runs
      if run["cpu_time_seconds"] is None or run["wall_time_seconds"] is None
  ]
  if missing_metrics:
    raise RuntimeError(
        f"screen result lacks parseable CPU or wall metrics: {missing_metrics}"
    )
  details = {row["task"]: row for row in manifest["tasks"]}
  rows = [
      {
          "task": run["task"],
          "phase_a_host": phase_a_host,
          "source": details[run["task"]]["source"],
          "family": details[run["task"]]["family"],
          "expected_verdict": run["expected_verdict"],
          "classification": classify_screen_result(run),
          "cpu_seconds": run["cpu_time_seconds"],
          "wall_seconds": run["wall_time_seconds"],
          "status": run["status"],
      }
      for run in runs
  ]
  output = Path(args.output_dir).resolve()
  if output.exists() and any(output.iterdir()):
    raise RuntimeError(f"output directory must be absent or empty: {output}")
  output.mkdir(parents=True, exist_ok=True)
  shutil.copytree(manifest_path.parent / "corpus", output / "corpus")
  fieldnames = list(rows[0])
  filenames = {
      "correct_fast": "correct-fast.csv",
      "analysis_survivor": "analysis-survivors.csv",
      "wrong_quarantine": "wrong-quarantine.csv",
      "verifier_failure_quarantine": "verifier-failure-quarantine.csv",
      "infrastructure_failure": "infrastructure-failure.csv",
  }
  for classification, filename in filenames.items():
    with (output / filename).open("w", newline="", encoding="utf-8") as target:
      writer = csv.DictWriter(target, fieldnames=fieldnames)
      writer.writeheader()
      writer.writerows(
          row for row in rows if row["classification"] == classification
      )
  with (output / "classification.csv").open(
      "w", newline="", encoding="utf-8"
  ) as target:
    writer = csv.DictWriter(target, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
  survivor_tasks = [
      row["task"] for row in rows if row["classification"] == "analysis_survivor"
  ]
  survivor_manifest = manifest_subset(
      manifest,
      survivor_tasks,
      {
          "operation": "phase_a_analysis_survivors",
          "parent_manifest_sha256": baseline.sha256_file(manifest_path),
          **provenance,
          "allowed_results": sorted(ANALYSIS_UNSOLVED),
          "phase_a_host": phase_a_host,
          "selection_independent_of_augmented_outcomes": True,
      },
  )
  survivor_path = output / "candidate-manifest-analysis-survivors.json"
  survivor_path.write_text(
      json.dumps(survivor_manifest, indent=2) + "\n", encoding="utf-8"
  )
  validate_manifest(survivor_path, args.sv_benchmarks)
  counts = collections.Counter(row["classification"] for row in rows)
  summary = {
      "task_count": len(rows),
      "phase_a_host": phase_a_host,
      "classifications": dict(sorted(counts.items())),
      **provenance,
      "survivor_manifest_sha256": baseline.sha256_file(survivor_path),
  }
  (output / "summary.json").write_text(
      json.dumps(summary, indent=2) + "\n", encoding="utf-8"
  )
  print(json.dumps(summary, sort_keys=True))


def command_screen_summary_plan(args):
  manifest_path = Path(args.manifest).resolve()
  manifest = validate_manifest(manifest_path, args.sv_benchmarks)
  host = manifest.get("derivation", {}).get("host")
  if args.phase_a_host != host or host not in DISCOVERY_HOSTS:
    raise RuntimeError("Phase-A host does not match manifest provenance")
  validate_screen_definition(
      args.benchmark_definition,
      manifest_path,
      manifest,
      args.sv_benchmarks,
  )
  rows = baseline.load_task_manifest(manifest_path)
  plan = load_screen_plan(
      args.screen_plan,
      rows,
      manifest_path,
      host,
      args.sv_benchmarks,
      args.benchmark_definition,
  )
  output = Path(args.output_dir).resolve()
  row_provenance_content = json.dumps({
      "schema_version": "hard-case-screen-row-provenance-v1",
      "screen_plan_sha256": plan["plan_sha256"],
      "primary_result_sha256": plan["primary_sha256"],
      "replacement_result_sha256": plan["replacement_sha256"],
      "rows": plan["row_sources"],
  }, indent=2) + "\n"
  write_screen_summary(
      args,
      manifest_path,
      manifest,
      host,
      [plan["rows"][task] for task in rows],
      {
          "screen_plan_sha256": plan["plan_sha256"],
          "result_sha256": [
              plan["primary_sha256"],
              *plan["replacement_sha256"],
          ],
          "row_provenance_sha256": hashlib.sha256(
              row_provenance_content.encode("utf-8")
          ).hexdigest(),
      },
  )
  (output / "row-provenance.json").write_text(
      row_provenance_content, encoding="utf-8"
  )


def declared_plan_file(root, entry, label):
  if (
      not isinstance(entry, dict)
      or set(entry) != {"path", "sha256"}
      or not isinstance(entry["path"], str)
      or not isinstance(entry["sha256"], str)
      or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
  ):
    raise RuntimeError(f"{label} must declare only path and sha256")
  relative = Path(entry["path"])
  if relative.is_absolute() or ".." in relative.parts:
    raise RuntimeError(f"{label} path must stay inside the repetition-plan directory")
  path = root / relative
  absolute = Path(os.path.abspath(path))
  if path.is_symlink() or not path.is_file() or path.resolve() != absolute:
    raise RuntimeError(f"{label} must be a regular non-symlink file")
  if baseline.sha256_file(path) != entry["sha256"]:
    raise RuntimeError(f"{label} hash does not match")
  return absolute


def plan_file_entry(path, root):
  declared = Path(path)
  path = declared.resolve()
  try:
    relative = path.relative_to(root)
  except ValueError as error:
    raise RuntimeError("repetition-plan inputs must stay inside its directory") from error
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != path
      or not path.is_file()
  ):
    raise RuntimeError(f"repetition-plan input must be a regular file: {path}")
  return {
      "path": relative.as_posix(),
      "sha256": baseline.sha256_file(path),
  }


def result_task_names(path, manifest):
  with baseline.open_result(Path(path)) as source:
    root = ET.parse(source).getroot()
  tasks = [
      baseline.match_result_task(run.get("name", ""), manifest)
      for run in root.findall("run")
  ]
  if len(tasks) != len(set(tasks)):
    raise RuntimeError("result contains duplicate task names")
  return tasks


def validate_taint_manifest(
    data,
    repetition,
    primary_hash,
    manifest,
    schema=FORMAL_TAINT_SCHEMA,
):
  if not isinstance(data, dict) or set(data) != {
      "schema_version",
      "repetition",
      "primary_result_sha256",
      "tasks",
  }:
    raise RuntimeError("formal taint manifest topology is not exact")
  if (
      data["schema_version"] != schema
      or not isinstance(data["repetition"], int)
      or data["repetition"] not in {1, 2}
      or data["repetition"] != repetition
      or data["primary_result_sha256"] != primary_hash
      or not isinstance(data["tasks"], list)
  ):
    raise RuntimeError("formal taint manifest identity does not match")
  tasks = {}
  for row in data["tasks"]:
    if (
        not isinstance(row, dict)
        or set(row) != {"task", "reason"}
        or not isinstance(row["task"], str)
        or not isinstance(row["reason"], str)
        or row["task"] not in manifest
        or row["reason"] not in FORMAL_TAINT_REASONS
        or row["task"] in tasks
    ):
      raise RuntimeError("formal taint task is invalid or duplicated")
    tasks[row["task"]] = row["reason"]
  if list(tasks) != sorted(tasks):
    raise RuntimeError("formal taint tasks must be sorted")
  return tasks


def read_proc_thread_stat(path):
  text = path.read_text(encoding="utf-8")
  fields = text[text.rfind(")") + 2 :].split()
  return (
      int(fields[11]) + int(fields[12]),
      int(fields[19]),
      int(fields[36]),
  )


def formal_systemd_unit(output_root, mode, label):
  root = Path(output_root).resolve()
  digest = sha256_text(f"{root}\0{mode}\0{label}")[:12]
  return f"vguide-{mode}-{label}-{digest}.scope"


def formal_process_descriptor(args, legacy=False, descriptor_schema=None):
  root = Path(args.output_root).resolve()
  definition = Path(args.definition).resolve()
  result_output = Path(args.result_output).resolve()
  monitor_output = Path(args.monitor_output).resolve()
  dataset_py = Path(args.dataset_py).resolve()
  cpachecker_dir = Path(args.cpachecker_dir).resolve()
  benchexec_dir = Path(args.benchexec_dir).resolve()
  python_bin = Path(args.python_bin).resolve()
  java_home = Path(args.java_home).resolve()
  for path, name in (
      (definition, "definition"),
      (result_output, "result output"),
      (monitor_output, "monitor output"),
      (dataset_py, "dataset script"),
  ):
    try:
      path.relative_to(root)
    except ValueError as error:
      raise RuntimeError(
          f"formal process {name} escapes output root"
      ) from error
  if (
      args.mode not in {"cap8", "cap16", "cap8-probe", "cap16-probe"}
      or args.p_cores != FORMAL_P_CORE_LIST
      or not isinstance(args.monitor_exclude_root, int)
      or args.monitor_exclude_root <= 0
  ):
    raise RuntimeError("formal process descriptor inputs are invalid")
  expected_host = (
      "athena" if args.mode in {"cap16", "cap16-probe"} else "valkyrie"
  )
  expected_python = (
      Path("/usr/bin/python3.12")
      if args.mode in {"cap16", "cap16-probe"}
      else Path("/usr/bin/python3.10")
  )
  recovery_root = dataset_py.parent.parent
  recovery_match = re.fullmatch(
      r"recovery-research-([0-9a-f]{40})", recovery_root.name
  )
  recovery_head = recovery_root / "research-head.txt"
  revision_runtime_is_pinned = (
      recovery_match is not None
      and recovery_root.parent == root / "input"
      and dataset_py == recovery_root / "scripts/dataset.py"
      and recovery_head.is_file()
      and not recovery_head.is_symlink()
      and recovery_head.read_text(encoding="utf-8")
      == f"{recovery_match.group(1)}\n"
  )
  if (
      args.host != expected_host
      or python_bin != expected_python
      or (
          dataset_py
          not in {
              root / "input/research/scripts/dataset.py",
              root / "input/recovery-research/scripts/dataset.py",
          }
          and not revision_runtime_is_pinned
      )
  ):
    raise RuntimeError("formal process descriptor runtime is not pinned")
  expected_name = (
      f"hard-case-dataset-v2-{args.mode.removesuffix('-probe')}"
      f"-cegar-probe-{args.host}-{args.label}"
      if is_strict_probe_mode(args.mode)
      else (
          f"hard-case-dataset-v2"
          f"{'-cap16' if args.mode == 'cap16' else ''}"
          f"-formal-{args.host}-{args.label}"
      )
  )
  if args.name != expected_name:
    raise RuntimeError("formal BenchExec run name is not canonical")
  unit = formal_systemd_unit(root, args.mode, args.label)
  schema = descriptor_schema or (
      LEGACY_FORMAL_PROCESS_DESCRIPTOR_SCHEMA
      if legacy
      else FORMAL_PROCESS_DESCRIPTOR_SCHEMA
  )
  if schema not in {
      FORMAL_PROCESS_DESCRIPTOR_SCHEMA,
      PREVIOUS_FORMAL_PROCESS_DESCRIPTOR_SCHEMA,
      LEGACY_FORMAL_PROCESS_DESCRIPTOR_SCHEMA,
  } or legacy != (schema == LEGACY_FORMAL_PROCESS_DESCRIPTOR_SCHEMA):
    raise RuntimeError("formal process descriptor schema is invalid")
  monitor_python_flags = (
      ("-I", "-B") if legacy else PYTHON_RUNTIME_FLAGS
  )
  benchexec_python_flags = ("-I",) if legacy else PYTHON_RUNTIME_FLAGS
  module_command = (
      LEGACY_BENCHEXEC_MODULE_COMMAND
      if legacy
      else BENCHEXEC_MODULE_COMMAND
  )
  monitor_argv = [
      str(python_bin),
      *monitor_python_flags,
      str(dataset_py),
      "monitor-formal-load",
      "--output",
      str(monitor_output),
      "--exclude-root",
      str(args.monitor_exclude_root),
  ]
  benchexec_argv = [
      "systemd-run",
      "--user",
      "--quiet",
      "--scope",
      f"--unit={unit}",
      "--slice=benchexec",
      "-p",
      "Delegate=yes",
      "taskset",
      "-c",
      args.p_cores,
      "env",
      "-i",
      "HOME=/home/benchexec",
      "LANG=C.UTF-8",
      "LC_ALL=C.UTF-8",
      "PATH=/usr/bin:/bin",
      f"JAVA={java_home}/bin/java",
      str(python_bin),
      *benchexec_python_flags,
      "-c",
      module_command,
      str(benchexec_dir),
      *((FORMAL_PYYAML_FILE,) if not legacy else ()),
      "--name",
      args.name,
      "--tool-directory",
      str(cpachecker_dir),
      "--outputpath",
      f"{result_output}/",
      "--allowedCores",
      args.p_cores,
      "--no-hyperthreading",
      "--container",
      "--read-only-dir",
      "/",
      "--hidden-dir",
      "/home",
      "--overlay-dir",
      str(cpachecker_dir),
      "-N",
      (
          "8"
          if is_strict_probe_mode(args.mode)
          else (
              "1"
              if schema == FORMAL_PROCESS_DESCRIPTOR_SCHEMA
              and args.mode == "cap16"
              else "2"
          )
      ),
      "-c",
      "1" if is_strict_probe_mode(args.mode) else "4",
      str(definition),
  ]
  return {
      "schema_version": schema,
      "output_root": str(root),
      "mode": args.mode,
      "label": args.label,
      "host": args.host,
      "inputs": {
          "name": args.name,
          "definition": str(definition),
          "result_output": str(result_output),
          "monitor_output": str(monitor_output),
          "monitor_exclude_root": args.monitor_exclude_root,
          "dataset_py": str(dataset_py),
          "cpachecker_dir": str(cpachecker_dir),
          "benchexec_dir": str(benchexec_dir),
          "python_bin": str(python_bin),
          "java_home": str(java_home),
          "p_cores": args.p_cores,
      },
      "systemd_unit": unit,
      "identities": {
          "benchexec-launcher": {
              "argv": benchexec_argv,
              "systemd_unit": unit,
          },
          "load-monitor": {
              "argv": monitor_argv,
              "systemd_unit": None,
          },
      },
  }


def trusted_legacy_process_descriptor(root, mode, label, host, path):
  root = Path(root).resolve()
  resolved = Path(path).resolve()
  if mode != "cap16" or host != "athena":
    raise RuntimeError("legacy process descriptor host is not selected")
  primary = LEGACY_CAP16_ATHENA_REPETITION_1
  replacement = FROZEN_CAP16_ATHENA_V2_RECOVERY_SELECTION
  if label == primary["label"]:
    validate_recovery_selection(root, primary)
    expected_path = root / "provenance" / (
        "repetition-1-process-descriptor.json"
    )
    expected_sha256 = primary["selected_provenance"][
        "repetition-1-process-descriptor.json"
    ]
  elif label == replacement["label"]:
    expected = replacement["files"]["process_descriptor"]
    expected_path = root / expected["path"]
    expected_sha256 = expected["sha256"]
  else:
    raise RuntimeError("legacy process descriptor has no frozen selection")
  if (
      resolved != expected_path
      or baseline.sha256_file(resolved) != expected_sha256
  ):
    raise RuntimeError("legacy process descriptor is not selected")


def load_formal_process_descriptor(path, output_root, mode, label, host):
  declared = Path(path)
  resolved = declared.resolve()
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != resolved
      or not resolved.is_file()
  ):
    raise RuntimeError("formal process descriptor is not a regular file")
  descriptor = json.loads(resolved.read_text(encoding="utf-8"))
  if (
      not isinstance(descriptor, dict)
      or set(descriptor) != {
          "schema_version",
          "output_root",
          "mode",
          "label",
          "host",
          "inputs",
          "systemd_unit",
          "identities",
      }
      or descriptor["schema_version"]
      not in {
          FORMAL_PROCESS_DESCRIPTOR_SCHEMA,
          PREVIOUS_FORMAL_PROCESS_DESCRIPTOR_SCHEMA,
          LEGACY_FORMAL_PROCESS_DESCRIPTOR_SCHEMA,
      }
      or descriptor["output_root"] != str(Path(output_root).resolve())
      or descriptor["mode"] != mode
      or descriptor["label"] != label
      or descriptor["host"] != host
      or not isinstance(descriptor["inputs"], dict)
  ):
    raise RuntimeError("formal process descriptor identity is invalid")
  legacy = (
      descriptor["schema_version"]
      == LEGACY_FORMAL_PROCESS_DESCRIPTOR_SCHEMA
  )
  if legacy:
    trusted_legacy_process_descriptor(
        output_root, mode, label, host, resolved
    )
  expected = formal_process_descriptor(argparse.Namespace(
      output_root=descriptor["output_root"],
      mode=descriptor["mode"],
      label=descriptor["label"],
      host=descriptor["host"],
      **descriptor["inputs"],
  ), legacy=legacy, descriptor_schema=descriptor["schema_version"])
  if descriptor != expected:
    raise RuntimeError("formal process descriptor content is invalid")
  return descriptor


def command_write_formal_process_descriptor(args):
  declared = Path(args.output)
  if declared.is_symlink():
    raise RuntimeError("formal process descriptor output is a symlink")
  output = declared.resolve()
  record = formal_process_descriptor(args)
  content = json.dumps(record, indent=2) + "\n"
  if output.exists():
    if output.read_text(encoding="utf-8") != content:
      raise RuntimeError("formal process descriptor already differs")
    return
  output.parent.mkdir(parents=True, exist_ok=True)
  temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
  temporary.write_text(content, encoding="utf-8")
  os.replace(temporary, output)


def command_formal_systemd_unit(args):
  print(formal_systemd_unit(args.output_root, args.mode, args.label))


def read_process_identity(pid, role):
  proc = Path("/proc") / str(pid)
  status = proc.joinpath("status").read_text(encoding="utf-8")
  uid = int(re.search(r"^Uid:\s+(\d+)", status, re.MULTILINE).group(1))
  stat_fields = proc.joinpath("stat").read_text(encoding="utf-8")
  starttime = int(stat_fields[stat_fields.rfind(")") + 2 :].split()[19])
  argv = [
      value.decode("utf-8", "surrogateescape")
      for value in proc.joinpath("cmdline").read_bytes().split(b"\0")
      if value
  ]
  return {
      "schema_version": FORMAL_PROCESS_IDENTITY_SCHEMA,
      "role": role,
      "uid": uid,
      "pid": pid,
      "proc_starttime": starttime,
      "argv": argv,
      "systemd_unit": None,
      "boot_id": read_boot_id(),
  }


def command_capture_process_identity(args):
  identity = read_process_identity(args.pid, args.role)
  output = Path(args.output)
  output.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")


def read_boot_id():
  boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
      encoding="ascii"
  ).strip()
  if re.fullmatch(
      r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
      r"[0-9a-f]{4}-[0-9a-f]{12}",
      boot_id,
  ) is None:
    raise RuntimeError("kernel boot identity is invalid")
  return boot_id


def load_owned_process_identity(path, trusted_legacy_sha256=None):
  path = Path(path)
  identity = json.loads(path.read_text(encoding="utf-8"))
  schema = identity.get("schema_version") if isinstance(identity, dict) else None
  fields = {
      "schema_version",
      "role",
      "uid",
      "pid",
      "proc_starttime",
      "argv",
      "systemd_unit",
  }
  if schema == FORMAL_PROCESS_IDENTITY_SCHEMA:
    fields.add("boot_id")
  elif not (
      schema == LEGACY_FORMAL_PROCESS_IDENTITY_SCHEMA
      and trusted_legacy_sha256 is not None
      and baseline.sha256_file(path) == trusted_legacy_sha256
  ):
    raise RuntimeError("owned process identity is invalid")
  if (
      not isinstance(identity, dict)
      or set(identity) != fields
      or identity["role"] not in {"load-monitor", "benchexec-launcher"}
      or type(identity["uid"]) is not int
      or identity["uid"] < 0
      or type(identity["pid"]) is not int
      or identity["pid"] <= 0
      or type(identity["proc_starttime"]) is not int
      or identity["proc_starttime"] <= 0
      or not isinstance(identity["argv"], list)
      or not identity["argv"]
      or any(not isinstance(value, str) or not value for value in identity["argv"])
      or (
          identity["systemd_unit"] is not None
          and (
              not isinstance(identity["systemd_unit"], str)
              or not identity["systemd_unit"]
          )
      )
      or (
          schema == FORMAL_PROCESS_IDENTITY_SCHEMA
          and (
              not isinstance(identity["boot_id"], str)
              or re.fullmatch(
                  r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                  r"[0-9a-f]{4}-[0-9a-f]{12}",
                  identity["boot_id"],
              ) is None
          )
      )
  ):
    raise RuntimeError("owned process identity is invalid")
  return identity


def require_process_gone(identity, systemd_unit=None):
  try:
    current = read_process_identity(identity["pid"], identity["role"])
  except (FileNotFoundError, ProcessLookupError):
    current = None
  if current is not None:
    current["systemd_unit"] = identity["systemd_unit"]
  if current == identity:
    raise RuntimeError("owned formal process is still alive; refusing resume")
  unit = identity["systemd_unit"] if systemd_unit is None else systemd_unit
  if unit is not None:
    result = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=LoadState",
            "--property=ActiveState",
            "--property=MainPID",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
      raise RuntimeError("cannot prove transient BenchExec unit is gone")
    state = dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if "=" in line
    )
    if (
        state.get("LoadState") != "not-found"
        and (
            state.get("ActiveState") not in {"inactive", "failed"}
            or state.get("MainPID") not in {None, "0", ""}
        )
    ):
      raise RuntimeError("transient BenchExec unit is still active")


def validate_formal_process_identity(identity, expected, require_unit=True):
  if (
      identity["role"] != expected["role"]
      or identity["uid"] != os.getuid()
      or identity["argv"] != expected["argv"]
      or (
          require_unit
          and identity["systemd_unit"] != expected["systemd_unit"]
      )
  ):
    raise RuntimeError("owned process identity does not match its descriptor")


def command_require_formal_process_gone(args):
  descriptor = load_formal_process_descriptor(
      args.descriptor, args.output_root, args.mode, args.label, args.host
  )
  identity = load_owned_process_identity(args.identity)
  expected = {
      "role": args.role,
      **descriptor["identities"][args.role],
  }
  validate_formal_process_identity(identity, expected, require_unit=False)
  require_process_gone(identity, descriptor["systemd_unit"] if (
      args.role == "benchexec-launcher"
  ) else None)
  validate_formal_process_identity(identity, expected)


def command_monitor_formal_load(args):
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"load-monitor output already exists: {output}")
  output.parent.mkdir(parents=True, exist_ok=True)
  clock_ticks = os.sysconf("SC_CLK_TCK")
  running = True

  def stop(*_):
    nonlocal running
    running = False

  signal.signal(signal.SIGTERM, stop)
  signal.signal(signal.SIGINT, stop)
  previous = {}
  previous_monotonic = time.monotonic()
  streaks = {}
  with output.open("x", encoding="utf-8", buffering=1) as target:
    target.write(json.dumps({
        "schema_version": FORMAL_LOAD_MONITOR_SCHEMA,
        "p_core_cpus": list(FORMAL_P_CORE_CPUS),
        "foreign_process_cpu_percent": FORMAL_FOREIGN_CPU_PERCENT,
        "minimum_consecutive_seconds": FORMAL_FOREIGN_CPU_SECONDS,
        "sample_interval_seconds": FORMAL_LOAD_SAMPLE_SECONDS,
        "excluded_process_root": args.exclude_root,
    }, sort_keys=True) + "\n")
    while running:
      time.sleep(FORMAL_LOAD_SAMPLE_SECONDS)
      now_monotonic = time.monotonic()
      elapsed = now_monotonic - previous_monotonic
      now = datetime.datetime.now().astimezone()
      processes = {}
      parents = {}
      for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
          continue
        try:
          status = (proc / "status").read_text(encoding="utf-8")
          parent = int(re.search(r"^PPid:\s+(\d+)$", status, re.MULTILINE).group(1))
          parents[int(proc.name)] = parent
        except (
            FileNotFoundError,
            PermissionError,
            ProcessLookupError,
            AttributeError,
            ValueError,
        ):
          continue
      excluded = {args.exclude_root}
      changed = True
      while changed:
        before = len(excluded)
        excluded.update(pid for pid, parent in parents.items() if parent in excluded)
        changed = len(excluded) != before
      current = {}
      for pid in parents:
        if pid in excluded:
          continue
        proc = Path("/proc") / str(pid)
        try:
          comm = (proc / "comm").read_text(encoding="utf-8").strip()
          uid = proc.stat().st_uid
          _, process_started, _ = read_proc_thread_stat(proc / "stat")
          for thread in (proc / "task").iterdir():
            ticks, thread_started, processor = read_proc_thread_stat(
                thread / "stat"
            )
            key = (pid, int(thread.name), thread_started)
            current[key] = ticks
            if key in previous and processor in FORMAL_P_CORE_CPUS:
              delta = ticks - previous[key]
              if delta >= 0:
                processes.setdefault(
                    pid, [0, uid, comm, process_started]
                )[0] += delta
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
          continue
      qualifying = {}
      for pid, (ticks, uid, comm, started) in processes.items():
        percent = ticks / clock_ticks / elapsed * 100
        if percent >= FORMAL_FOREIGN_CPU_PERCENT:
          qualifying[(pid, started)] = (percent, uid, comm)
      for key in set(streaks) - set(qualifying):
        del streaks[key]
      offenders = []
      for key, (percent, uid, comm) in sorted(qualifying.items()):
        if key not in streaks:
          streaks[key] = (
              previous_monotonic,
              now - datetime.timedelta(seconds=elapsed),
          )
        since_monotonic, since = streaks[key]
        duration = now_monotonic - since_monotonic
        offenders.append({
            "pid": key[0],
            "uid": uid,
            "comm": comm,
            "cpu_percent": round(percent, 3),
            "duration_seconds": round(duration, 3),
            "since": since.isoformat(),
            "contended": duration >= FORMAL_FOREIGN_CPU_SECONDS,
        })
      target.write(json.dumps({
          "timestamp": now.isoformat(),
          "elapsed_seconds": round(elapsed, 6),
          "offenders": offenders,
      }, sort_keys=True) + "\n")
      previous = current
      previous_monotonic = now_monotonic


def formal_attempt_path(root, value, label):
  declared = Path(value)
  path = declared.resolve()
  try:
    relative = path.relative_to(root)
  except ValueError as error:
    raise RuntimeError(f"{label} escapes formal output") from error
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != path
      or not path.is_file()
  ):
    raise RuntimeError(f"{label} is not a regular file")
  return path, relative.as_posix()


def machine_check_record(before, after):
  before_data = json.loads(before.read_text(encoding="utf-8"))
  after_data = json.loads(after.read_text(encoding="utf-8"))
  if before_data.get("hostname") != after_data.get("hostname"):
    raise RuntimeError("attempt machine snapshots have different hosts")
  deltas = {}
  for name in (
      "package_throttle_count",
      "package_throttle_total_time_ms",
      "pswpin_pages",
      "pswpout_pages",
  ):
    start = int(before_data["measurement_counters"][name])
    end = int(after_data["measurement_counters"][name])
    if end < start:
      raise RuntimeError(f"attempt machine counter decreased: {name}")
    deltas[name] = end - start
  changed = any(deltas.values())
  return {
      "hostname": before_data["hostname"],
      "accepted": True,
      "stable": not changed,
      "counter_deltas": deltas,
      "warnings": (
          ["thermal throttling or swap activity observed"] if changed else []
      ),
  }


def current_uptime_ticks():
  uptime = float(
      Path("/proc/uptime").read_text(encoding="ascii").split()[0]
  )
  return int(uptime * os.sysconf("SC_CLK_TCK"))


def recovery_process_boot_binding(identities):
  schemas = {identity["schema_version"] for identity in identities.values()}
  if schemas == {FORMAL_PROCESS_IDENTITY_SCHEMA}:
    captured = {identity["boot_id"] for identity in identities.values()}
    if len(captured) != 1:
      raise RuntimeError("formal processes have different boot identities")
    captured_boot = captured.pop()
    recovery_boot = read_boot_id()
    return {
        "method": "captured-boot-id",
        "captured_boot_id": captured_boot,
        "recovery_boot_id": recovery_boot,
        "rebooted": captured_boot != recovery_boot,
    }
  if schemas == {LEGACY_FORMAL_PROCESS_IDENTITY_SCHEMA}:
    uptime_ticks = current_uptime_ticks()
    starttimes = {
        role: identity["proc_starttime"]
        for role, identity in sorted(identities.items())
    }
    if any(starttime <= uptime_ticks for starttime in starttimes.values()):
      raise RuntimeError(
          "legacy formal process identities are not bound across reboot"
      )
    return {
        "method": "legacy-reboot-uptime",
        "recovery_boot_id": read_boot_id(),
        "recovery_uptime_ticks": uptime_ticks,
        "captured_proc_starttimes": starttimes,
        "rebooted": True,
    }
  raise RuntimeError("formal process identity schemas do not match")


def validate_recovery_process_boot_binding(binding, identities):
  schemas = {identity["schema_version"] for identity in identities.values()}
  if schemas == {FORMAL_PROCESS_IDENTITY_SCHEMA}:
    captured = {identity["boot_id"] for identity in identities.values()}
    expected = {
        "method": "captured-boot-id",
        "captured_boot_id": next(iter(captured)) if len(captured) == 1 else None,
        "recovery_boot_id": binding.get("recovery_boot_id"),
        "rebooted": (
            len(captured) == 1
            and next(iter(captured)) != binding.get("recovery_boot_id")
        ),
    }
    if (
        not isinstance(binding.get("recovery_boot_id"), str)
        or re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}",
            binding["recovery_boot_id"],
        ) is None
        or binding != expected
    ):
      raise RuntimeError("formal recovery boot binding is invalid")
    return
  if schemas == {LEGACY_FORMAL_PROCESS_IDENTITY_SCHEMA}:
    starttimes = {
        role: identity["proc_starttime"]
        for role, identity in sorted(identities.items())
    }
    expected = {
        "method": "legacy-reboot-uptime",
        "recovery_boot_id": binding.get("recovery_boot_id"),
        "recovery_uptime_ticks": binding.get("recovery_uptime_ticks"),
        "captured_proc_starttimes": starttimes,
        "rebooted": True,
    }
    if (
        type(binding.get("recovery_uptime_ticks")) is not int
        or binding["recovery_uptime_ticks"] <= 0
        or any(
            starttime <= binding["recovery_uptime_ticks"]
            for starttime in starttimes.values()
        )
        or not isinstance(binding.get("recovery_boot_id"), str)
        or re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}",
            binding["recovery_boot_id"],
        ) is None
        or binding != expected
    ):
      raise RuntimeError("legacy formal recovery boot binding is invalid")
    return
  raise RuntimeError("formal process identity schemas do not match")


def recovered_machine_check_record(before, after, process_boot_binding):
  before_data = json.loads(before.read_text(encoding="utf-8"))
  after_data = json.loads(after.read_text(encoding="utf-8"))
  identity = (
      "hostname",
      "platform",
      "kernel",
      "cpu_model",
      "online_cpus",
      "allowed_p_core_cpus",
      "java_version",
  )
  if any(
      before_data.get(name) is None
      or before_data.get(name) != after_data.get(name)
      for name in identity
  ):
    raise RuntimeError("recovered attempt machine identity changed")
  if not process_boot_binding["rebooted"]:
    record = machine_check_record(before, after)
    record["recovery"] = "authenticated-process-gone"
    record["process_boot_binding"] = process_boot_binding
    return record
  return {
      "hostname": before_data["hostname"],
      "accepted": True,
      "stable": None,
      "counter_deltas": None,
      "warnings": [
          "machine counter deltas unavailable after markerless interruption"
      ],
      "recovery": "authenticated-process-gone",
      "process_boot_binding": process_boot_binding,
  }


def validate_monitor_stop_evidence(path, pid, mode, benchexec_exit):
  entries = []
  for line in Path(path).read_text(encoding="utf-8").splitlines():
    if line.count("=") != 1:
      raise RuntimeError("formal attempt monitor stop evidence is invalid")
    entries.append(line.split("=", 1))
  stopped = dict(entries)
  normal = stopped == {
      "pid": str(pid),
      "exit": "0",
      "samples": stopped.get("samples"),
  }
  recovered = stopped == {
      "pid": str(pid),
      "exit": "unobserved",
      "samples": stopped.get("samples"),
      "recovery": "authenticated-process-gone",
  }
  if (
      len(entries) != len(stopped)
      or (not normal and not recovered)
      or not stopped["samples"].isdigit()
      or int(stopped["samples"]) <= 0
      or (
          normal
          and benchexec_exit not in {0, 130}
          and (not is_strict_probe_mode(mode) or benchexec_exit != 125)
      )
      or (
          recovered
          and (
              benchexec_exit != 125
              or (mode != "cap16" and not is_strict_probe_mode(mode))
          )
      )
  ):
    raise RuntimeError("formal attempt monitor stop evidence is invalid")
  return recovered


def formal_attempt_record(args):
  root = Path(args.output_root).resolve()
  manifest_path = Path(args.manifest).resolve()
  manifest = baseline.load_task_manifest(manifest_path)
  paths = {}
  for name in (
      "definition",
      "result",
      "benchexec_log",
      "benchexec_process",
      "process_descriptor",
      "load_monitor",
      "monitor_pid",
      "monitor_process",
      "monitor_stopped",
      "machine_before",
      "machine_after",
      "machine_check",
  ):
    path, relative = formal_attempt_path(
        root, getattr(args, name), name.replace("_", " ")
    )
    paths[name] = (path, relative)
  result_tasks = result_task_names(paths["result"][0], manifest)
  subset = {task: manifest[task] for task in result_tasks}
  subset_manifest = {
      "task_count": len(result_tasks),
      "tasks": [manifest[task] for task in result_tasks],
  }
  if is_strict_probe_mode(args.mode):
    validate_probe_definition(
        paths["definition"][0],
        manifest_path,
        subset_manifest,
        args.sv_benchmarks,
    )
    metadata = probe_result_metadata(
        paths["result"][0], allow_incomplete=True
    )
  else:
    validate_formal_definition(
        paths["definition"][0],
        manifest_path,
        subset_manifest,
        args.sv_benchmarks,
    )
    metadata = result_metadata(
        paths["result"][0], FORMAL_DISPLAY, "900 s", allow_incomplete=True
    )
  if metadata["host"] != args.host:
    raise RuntimeError("formal attempt host is invalid")
  validate_result_run_topology(
      paths["result"][0],
      subset,
      args.sv_benchmarks,
      paths["definition"][0],
  )
  if not paths["benchexec_log"][0].read_text(
      encoding="utf-8", errors="replace"
  ):
    raise RuntimeError("formal attempt BenchExec log is empty")
  trusted_identities = getattr(args, "trusted_legacy_identity_hashes", {})
  benchexec_identity = load_attempt_process_identity(
      paths["benchexec_process"][0],
      root,
      args.label,
      trusted_identities.get("benchexec_process"),
  )
  process_descriptor = load_formal_process_descriptor(
      paths["process_descriptor"][0],
      root,
      args.mode,
      args.label,
      args.host,
  )
  with paths["load_monitor"][0].open("rb") as monitor_file:
    monitor_header = json.loads(monitor_file.readline().decode("utf-8"))
  descriptor_inputs = process_descriptor["inputs"]
  if (
      descriptor_inputs["definition"] != str(paths["definition"][0])
      or descriptor_inputs["result_output"] != str(paths["result"][0].parent)
      or descriptor_inputs["monitor_output"] != str(paths["load_monitor"][0])
      or descriptor_inputs["monitor_exclude_root"]
      != monitor_header["excluded_process_root"]
  ):
    raise RuntimeError(
        "formal process descriptor does not match attempt evidence"
    )
  if (
      benchexec_identity.get("role") != "benchexec-launcher"
      or benchexec_identity.get("uid") != os.getuid()
  ):
    raise RuntimeError("formal BenchExec process identity is invalid")
  validate_formal_process_identity(benchexec_identity, {
      "role": "benchexec-launcher",
      **process_descriptor["identities"]["benchexec-launcher"],
  })
  require_process_gone(
      benchexec_identity, process_descriptor["systemd_unit"]
  )
  pid = int(paths["monitor_pid"][0].read_text(encoding="utf-8"))
  process_identity = load_attempt_process_identity(
      paths["monitor_process"][0],
      root,
      args.label,
      trusted_identities.get("monitor_process"),
  )
  if (
      process_identity.get("pid") != pid
      or process_identity.get("uid") != os.getuid()
      or process_identity.get("role") != "load-monitor"
  ):
    raise RuntimeError("formal attempt monitor process identity is invalid")
  validate_formal_process_identity(process_identity, {
      "role": "load-monitor",
      **process_descriptor["identities"]["load-monitor"],
  })
  require_process_gone(process_identity)
  recovered = validate_monitor_stop_evidence(
      paths["monitor_stopped"][0], pid, args.mode, args.benchexec_exit
  )
  actual_check = json.loads(
      paths["machine_check"][0].read_text(encoding="utf-8")
  )
  if recovered:
    if not metadata["incomplete"]:
      raise RuntimeError("recovered formal attempt result is not incomplete")
    identities = {
        "benchexec-launcher": benchexec_identity,
        "load-monitor": process_identity,
    }
    allow_final_log_only_completion = (
        validate_markerless_recovery_identity_selection(
            root,
            args.label,
            args.role,
            args.repetition,
            {name: path for name, (path, _) in paths.items()},
            identities,
            args.sv_benchmarks,
        )
    )
    run_taints(
        paths["result"][0],
        paths["benchexec_log"][0],
        paths["load_monitor"][0],
        manifest,
        allow_trailing_nul=True,
        allow_final_log_only_completion=allow_final_log_only_completion,
    )
    binding = actual_check.get("process_boot_binding")
    if not isinstance(binding, dict):
      raise RuntimeError("formal recovery boot binding is missing")
    validate_recovery_process_boot_binding(binding, identities)
    expected_check = recovered_machine_check_record(
        paths["machine_before"][0], paths["machine_after"][0], binding
    )
    recovery_relatives = {
        name: Path(paths[name][1])
        for name in ("monitor_stopped", "machine_after", "machine_check")
    }
    versioned = [
        relative.parts[:2] == ("provenance", "recoveries")
        for relative in recovery_relatives.values()
    ]
    if any(versioned):
      parents = {relative.parent for relative in recovery_relatives.values()}
      if (
          not all(versioned)
          or len(parents) != 1
          or len(next(iter(parents)).parts) != 4
      ):
        raise RuntimeError(
            "formal recovery evidence namespace identity is invalid"
        )
      parent = next(iter(parents))
      expected_paths = formal_recovery_evidence_paths(
          root, args.label, parent.name
      )
      if any(
          paths[name][0] != expected_paths[name]
          for name in expected_paths
      ) or not recovery_evidence_namespace_complete(expected_paths):
        raise RuntimeError(
            "formal recovery evidence namespace identity is invalid"
        )
      revision_provenance = (
          root / f"input/recovery-research-{parent.name}"
      )
      original_provenance = root / "input/research"
      if revision_provenance.exists() or revision_provenance.is_symlink():
        recovery_provenance = revision_provenance
      elif (
          original_provenance.is_dir()
          and not original_provenance.is_symlink()
          and original_provenance.joinpath("research-head.txt").is_file()
          and original_provenance.joinpath(
              "research-head.txt"
          ).read_text(encoding="utf-8")
          == f"{parent.name}\n"
      ):
        recovery_provenance = original_provenance
      else:
        raise RuntimeError(
            "formal recovery research provenance is missing"
        )
      if (
          formal_recovery_research_head(
              root, recovery_provenance, args.mode
          )
          != parent.name
      ):
        raise RuntimeError(
            "formal recovery research provenance is invalid"
        )
    else:
      historical_paths = {
          "monitor_stopped": (
              root / f"provenance/{args.label}-load-monitor.jsonl.stopped"
          ),
          "machine_after": (
              root / f"provenance/machine-after-{args.label}.json"
          ),
          "machine_check": (
              root / f"provenance/machine-check-{args.label}.json"
          ),
      }
      if any(
          paths[name][0] != historical_paths[name]
          for name in historical_paths
      ):
        raise RuntimeError(
            "formal recovery evidence namespace identity is invalid"
        )
  else:
    load_formal_contention_intervals(paths["load_monitor"][0])
    expected_check = machine_check_record(
        paths["machine_before"][0], paths["machine_after"][0]
    )
  if expected_check["hostname"] != args.host:
    raise RuntimeError("formal attempt machine host is invalid")
  if actual_check != expected_check:
    raise RuntimeError("formal attempt machine check is invalid")
  return {
      "schema_version": FORMAL_ATTEMPT_SCHEMA,
      "mode": args.mode,
      "host": args.host,
      "manifest_sha256": baseline.sha256_file(manifest_path),
      "label": args.label,
      "role": args.role,
      "repetition": args.repetition,
      "benchexec_exit": args.benchexec_exit,
      "result_tasks": sorted(result_tasks),
      "result_incomplete": metadata["incomplete"],
      "files": {
          name: {
              "path": relative,
              "sha256": baseline.sha256_file(path),
          }
          for name, (path, relative) in sorted(paths.items())
      },
  }


def validate_formal_attempt_marker(
    marker_path, root, manifest_path, sv_benchmarks, host, mode
):
  marker = Path(marker_path).resolve()
  record = json.loads(marker.read_text(encoding="utf-8"))
  if (
      isinstance(record, dict)
      and record.get("schema_version") == LEGACY_FORMAL_ATTEMPT_SCHEMA
  ):
    return validate_legacy_v3_attempt_marker(
        marker, root, manifest_path, sv_benchmarks, host, mode
    )
  if (
      not isinstance(record, dict)
      or set(record) != {
          "schema_version",
          "mode",
          "host",
          "manifest_sha256",
          "label",
          "role",
          "repetition",
          "benchexec_exit",
          "result_tasks",
          "result_incomplete",
          "files",
      }
      or record["schema_version"] != FORMAL_ATTEMPT_SCHEMA
      or record["mode"] != mode
      or record["host"] != host
      or record["manifest_sha256"] != baseline.sha256_file(manifest_path)
      or record["role"] not in {"primary", "replacement"}
      or marker.stem != record["label"]
      or not isinstance(record["files"], dict)
      or set(record["files"]) != {
          "definition",
          "result",
          "benchexec_log",
          "benchexec_process",
          "process_descriptor",
          "load_monitor",
          "monitor_pid",
          "monitor_process",
          "monitor_stopped",
          "machine_before",
          "machine_after",
          "machine_check",
      }
  ):
    raise RuntimeError("formal attempt marker schema or identity is invalid")
  canonical_label = (
      f"repetition-{record['repetition']}"
      if record["role"] == "primary"
      else rf"repetition-{record['repetition']}-replacement-attempt-[1-9]\d*"
  )
  if (
      record["label"] != canonical_label
      if record["role"] == "primary"
      else re.fullmatch(canonical_label, record["label"]) is None
  ):
    raise RuntimeError("formal attempt marker label is not canonical")
  args = argparse.Namespace(
      output_root=str(root),
      manifest=str(manifest_path),
      sv_benchmarks=str(sv_benchmarks),
      host=host,
      mode=mode,
      label=record["label"],
      role=record["role"],
      repetition=record["repetition"],
      benchexec_exit=record["benchexec_exit"],
      **{
          name: str(Path(root) / entry["path"])
          for name, entry in record["files"].items()
      },
  )
  expected = formal_attempt_record(args)
  if expected != record:
    raise RuntimeError("formal attempt marker content is invalid")
  return record


def validate_legacy_v3_attempt_marker(
    marker_path, root, manifest_path, sv_benchmarks, host, mode
):
  marker = Path(marker_path).resolve()
  root = Path(root).resolve()
  record = json.loads(marker.read_text(encoding="utf-8"))
  file_names = {
      "definition",
      "result",
      "benchexec_log",
      "benchexec_process",
      "process_descriptor",
      "load_monitor",
      "monitor_pid",
      "monitor_process",
      "monitor_stopped",
      "machine_before",
      "machine_after",
      "machine_check",
  }
  if (
      not isinstance(record, dict)
      or set(record) != {
          "schema_version",
          "mode",
          "host",
          "manifest_sha256",
          "label",
          "role",
          "repetition",
          "benchexec_exit",
          "result_tasks",
          "result_incomplete",
          "files",
      }
      or record["schema_version"] != LEGACY_FORMAL_ATTEMPT_SCHEMA
      or record["mode"] != mode
      or record["host"] != host
      or record["manifest_sha256"] != baseline.sha256_file(manifest_path)
      or record["role"] not in {"primary", "replacement"}
      or marker.stem != record["label"]
      or record["benchexec_exit"] not in {0, 130}
      or not isinstance(record["files"], dict)
      or set(record["files"]) != file_names
  ):
    raise RuntimeError("legacy formal attempt marker is invalid")
  canonical_label = (
      f"repetition-{record['repetition']}"
      if record["role"] == "primary"
      else rf"repetition-{record['repetition']}-replacement-attempt-[1-9]\d*"
  )
  if (
      record["label"] != canonical_label
      if record["role"] == "primary"
      else re.fullmatch(canonical_label, record["label"]) is None
  ):
    raise RuntimeError("legacy formal attempt marker label is not canonical")
  paths = {}
  for name, entry in record["files"].items():
    if (
        not isinstance(entry, dict)
        or set(entry) != {"path", "sha256"}
        or not isinstance(entry["path"], str)
        or not isinstance(entry["sha256"], str)
    ):
      raise RuntimeError("legacy formal attempt file record is invalid")
    path, relative = formal_attempt_path(root, root / entry["path"], name)
    if relative != entry["path"] or baseline.sha256_file(path) != entry["sha256"]:
      raise RuntimeError("legacy formal attempt file hash differs")
    paths[name] = str(path)
  args = argparse.Namespace(
      output_root=str(root),
      manifest=str(Path(manifest_path).resolve()),
      sv_benchmarks=str(sv_benchmarks),
      host=host,
      mode=mode,
      label=record["label"],
      role=record["role"],
      repetition=record["repetition"],
      benchexec_exit=record["benchexec_exit"],
      trusted_legacy_identity_hashes={
          name: record["files"][name]["sha256"]
          for name in ("benchexec_process", "monitor_process")
      },
      **paths,
  )
  expected = formal_attempt_record(args)
  expected["schema_version"] = LEGACY_FORMAL_ATTEMPT_SCHEMA
  if expected != record:
    raise RuntimeError("legacy formal attempt marker content is invalid")
  return expected


def command_formal_attempt_complete(args):
  output = Path(args.output).resolve()
  if output.exists():
    current = json.loads(output.read_text(encoding="utf-8"))
    if current.get("schema_version") == LEGACY_FORMAL_ATTEMPT_SCHEMA:
      record = validate_legacy_v3_attempt_marker(
          output,
          Path(args.output_root).resolve(),
          Path(args.manifest).resolve(),
          args.sv_benchmarks,
          args.host,
          args.mode,
      )
      for name in record["files"]:
        expected = (
            Path(args.output_root).resolve()
            / record["files"][name]["path"]
        ).resolve()
        if Path(getattr(args, name)).resolve() != expected:
          raise RuntimeError(
              "legacy formal attempt invocation does not match marker"
          )
      for name in ("label", "role", "repetition", "benchexec_exit"):
        if getattr(args, name) != record[name]:
          raise RuntimeError(
              "legacy formal attempt invocation does not match marker"
          )
    else:
      record = formal_attempt_record(args)
  else:
    record = formal_attempt_record(args)
  content = json.dumps(record, indent=2) + "\n"
  if output.exists():
    if output.read_text(encoding="utf-8") != content:
      raise RuntimeError("formal attempt completion marker is invalid")
  else:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, output)
  validate_formal_attempt_marker(
      output,
      Path(args.output_root).resolve(),
      Path(args.manifest).resolve(),
      args.sv_benchmarks,
      args.host,
      args.mode,
  )
  print(output)


def command_validate_formal_attempt(args):
  root = Path(args.output_root).resolve()
  record = validate_formal_attempt_marker(
      args.marker,
      root,
      Path(args.manifest).resolve(),
      args.sv_benchmarks,
      args.host,
      args.mode,
  )
  expected = {
      "label": args.label,
      "role": args.role,
      "repetition": args.repetition,
  }
  if any(record[name] != value for name, value in expected.items()):
    raise RuntimeError("formal attempt marker invocation is invalid")
  for name in ("definition", "result"):
    recorded = (root / record["files"][name]["path"]).resolve()
    if recorded != Path(getattr(args, name)).resolve():
      raise RuntimeError("formal attempt marker invocation is invalid")
  print(record["benchexec_exit"])


def recovery_path(root, value, label, must_exist):
  declared = Path(value)
  if declared.is_symlink():
    raise RuntimeError(f"formal recovery {label} is a symlink")
  path = declared.resolve()
  try:
    path.relative_to(root)
  except ValueError as error:
    raise RuntimeError(f"formal recovery {label} escapes output root") from error
  if Path(os.path.abspath(declared)) != path:
    raise RuntimeError(f"formal recovery {label} path is not canonical")
  if must_exist and not path.is_file():
    raise RuntimeError(f"formal recovery {label} is not a regular file")
  if not must_exist and path.exists() and not path.is_file():
    raise RuntimeError(f"formal recovery {label} is not a regular file")
  return path


def write_recovery_evidence(path, content):
  if path.exists():
    if path.read_text(encoding="utf-8") != content:
      raise RuntimeError(f"formal recovery evidence already differs: {path}")
    return
  path.parent.mkdir(parents=True, exist_ok=True)
  temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
  try:
    with temporary.open("x", encoding="utf-8") as evidence:
      evidence.write(content)
      evidence.flush()
      os.fsync(evidence.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
      os.fsync(directory)
    finally:
      os.close(directory)
  finally:
    temporary.unlink(missing_ok=True)


def formal_recovery_research_head(root, value, mode):
  declared = Path(value)
  provenance = declared.resolve()
  try:
    relative = provenance.relative_to(root)
  except ValueError as error:
    raise RuntimeError(
        "formal recovery research provenance escapes output root"
    ) from error
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != provenance
      or not provenance.is_dir()
  ):
    raise RuntimeError(
        "formal recovery research provenance is not a canonical directory"
    )
  expected_files = {
      "inventory.sha256",
      "research-diff.patch",
      "research-head.txt",
      "research-index-flags.txt",
      "research-state.json",
      "research-status.porcelain",
      "scripts/baseline.py",
      "scripts/dataset.py",
      "scripts/run-stock-formal-dataset.sh",
  }
  if mode == "cap16":
    expected_files.add("scripts/run-stock-cap16-formal-dataset.sh")
  actual_files = set()
  actual_directories = set()
  for path in provenance.rglob("*"):
    if path.is_symlink():
      raise RuntimeError(
          "formal recovery research provenance contains a symlink"
      )
    entry = path.relative_to(provenance).as_posix()
    if path.is_dir():
      actual_directories.add(entry)
    elif path.is_file():
      actual_files.add(entry)
    else:
      raise RuntimeError(
          "formal recovery research provenance topology is invalid"
      )
  if actual_directories != {"scripts"} or actual_files != expected_files:
    raise RuntimeError(
        "formal recovery research provenance topology is invalid"
    )
  head_text = (provenance / "research-head.txt").read_text(encoding="utf-8")
  if re.fullmatch(r"[0-9a-f]{40}\n", head_text) is None:
    raise RuntimeError("formal recovery research head is invalid")
  head = head_text.rstrip("\n")
  expected_relative = {
      Path("input/research"),
      Path(f"input/recovery-research-{head}"),
  }
  if relative not in expected_relative:
    raise RuntimeError(
        "formal recovery research path does not match its head"
    )
  empty_hash = hashlib.sha256(b"").hexdigest()
  expected_state = {
      "head": head,
      "clean": True,
      "status_sha256": empty_hash,
      "diff_sha256": empty_hash,
  }
  if (
      (provenance / "research-status.porcelain").read_bytes()
      or (provenance / "research-diff.patch").read_bytes()
      or json.loads(
          (provenance / "research-state.json").read_text(encoding="utf-8")
      )
      != expected_state
  ):
    raise RuntimeError("formal recovery research state is invalid")
  inventory = "".join(
      f"{baseline.sha256_file(provenance / relative_path)}  "
      f"{relative_path}\n"
      for relative_path in sorted(expected_files - {"inventory.sha256"})
  )
  if (
      provenance.joinpath("inventory.sha256").read_text(encoding="utf-8")
      != inventory
  ):
    raise RuntimeError("formal recovery research inventory is invalid")
  return head


def formal_recovery_evidence_paths(root, label, research_head):
  if (
      re.fullmatch(
          r"repetition-[12](?:-replacement-attempt-[1-9]\d*)?", label
      )
      is None
      or re.fullmatch(r"[0-9a-f]{40}", research_head) is None
  ):
    raise RuntimeError("formal recovery evidence identity is invalid")
  directory = (
      Path(root).resolve()
      / "provenance/recoveries"
      / label
      / research_head
  )
  return {
      "monitor_stopped": directory / "monitor-stopped",
      "machine_after": directory / "machine-after.json",
      "machine_check": directory / "machine-check.json",
  }


def recovery_evidence_namespace_complete(paths):
  directory = paths["monitor_stopped"].parent
  if not directory.exists():
    return False
  if directory.is_symlink() or not directory.is_dir():
    raise RuntimeError("formal recovery evidence namespace is invalid")
  expected = {path.name for path in paths.values()}
  actual = {path.name for path in directory.iterdir()}
  if actual != expected or any(
      path.is_symlink() or not path.is_file() for path in directory.iterdir()
  ):
    raise RuntimeError("formal recovery evidence topology is invalid")
  return True


def formal_recovery_preparation_paths(paths):
  directory = paths["monitor_stopped"].parent
  prepared = directory.with_name(f".{directory.name}.preparing")
  return {
      name: prepared / path.name for name, path in paths.items()
  }


def recovery_preparation_complete(paths):
  directory = paths["monitor_stopped"].parent
  if not directory.exists():
    return False
  if directory.is_symlink() or not directory.is_dir():
    raise RuntimeError("formal recovery preparation is invalid")
  expected = {path.name for path in paths.values()}
  entries = list(directory.iterdir())
  actual = {entry.name for entry in entries}
  if actual == expected and all(
      not entry.is_symlink() and entry.is_file() for entry in entries
  ):
    return True
  allowed_temporary = re.compile(
      r"^\.(?:monitor-stopped|machine-after\.json|machine-check\.json)"
      r"\.(?:tmp|capture)-[1-9]\d*$"
  )
  if any(
      entry.is_symlink()
      or not entry.is_file()
      or (
          entry.name not in expected
          and allowed_temporary.fullmatch(entry.name) is None
      )
      for entry in entries
  ):
    raise RuntimeError("formal recovery preparation topology is invalid")
  return False


def discard_incomplete_recovery_preparation(paths):
  directory = paths["monitor_stopped"].parent
  if not directory.exists():
    return
  if directory.is_symlink() or not directory.is_dir():
    raise RuntimeError("formal recovery preparation is invalid")
  allowed = {path.name for path in paths.values()}
  temporary = re.compile(
      r"^\.(?:monitor-stopped|machine-after\.json|machine-check\.json)"
      r"\.(?:tmp|capture)-[1-9]\d*$"
  )
  entries = list(directory.iterdir())
  if any(
      entry.is_symlink()
      or not entry.is_file()
      or (
          entry.name not in allowed
          and temporary.fullmatch(entry.name) is None
      )
      for entry in entries
  ):
    raise RuntimeError("formal recovery preparation topology is invalid")
  for entry in entries:
    entry.unlink()
  directory.rmdir()
  descriptor = os.open(directory.parent, os.O_RDONLY)
  try:
    os.fsync(descriptor)
  finally:
    os.close(descriptor)


def publish_recovery_preparation(prepared, published):
  source = prepared["monitor_stopped"].parent
  target = published["monitor_stopped"].parent
  if target.exists() or target.is_symlink():
    raise RuntimeError("formal recovery evidence namespace already exists")
  os.rename(source, target)
  descriptor = os.open(target.parent, os.O_RDONLY)
  try:
    os.fsync(descriptor)
  finally:
    os.close(descriptor)


def validate_stored_recovery_evidence(
    paths, machine_before, identities, stop_content
):
  write_recovery_evidence(paths["monitor_stopped"], stop_content)
  actual_check = json.loads(
      paths["machine_check"].read_text(encoding="utf-8")
  )
  binding = actual_check.get("process_boot_binding")
  if not isinstance(binding, dict):
    raise RuntimeError("formal recovery boot binding is missing")
  validate_recovery_process_boot_binding(binding, identities)
  check = recovered_machine_check_record(
      machine_before, paths["machine_after"], binding
  )
  write_recovery_evidence(
      paths["machine_check"], json.dumps(check, sort_keys=True) + "\n"
  )


def formal_result_directory_digest(directory):
  directory = Path(directory)
  lines = []
  for path in sorted(directory.rglob("*")):
    if path.is_symlink():
      raise RuntimeError("formal recovery result tree contains a symlink")
    if path.is_file():
      lines.append(
          f"{baseline.sha256_file(path)}  "
          f"{path.relative_to(directory).as_posix()}\n"
      )
  return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def validate_markerless_recovery_identity_selection(
    root,
    label,
    role,
    repetition,
    paths,
    identities,
    sv_benchmarks=None,
):
  schemas = {identity["schema_version"] for identity in identities.values()}
  if schemas == {LEGACY_FORMAL_PROCESS_IDENTITY_SCHEMA}:
    return False
  if schemas != {FORMAL_PROCESS_IDENTITY_SCHEMA}:
    raise RuntimeError("formal process identity schemas do not match")
  root = Path(root).resolve()
  authorization_path = root / f"provenance/authorizations/{label}.json"
  if authorization_path.is_file() and not authorization_path.is_symlink():
    if sv_benchmarks is None:
      raise RuntimeError("formal recovery SV-Benchmarks root is missing")
    protocol_root = root / "input/recovery-protocol"
    protocol_path = protocol_root / "protocol.json"
    seed_path = protocol_root / "seed-ledger.json"
    manifest_path = protocol_root / "candidate-manifest.json"
    property_file = protocol_root / "unreach-call.prp"
    state = load_formal_recovery_ledger(
        root,
        protocol_path,
        seed_path,
        manifest_path,
        property_file,
        sv_benchmarks,
    )
    authorization = formal_recovery_authorization(
        root, authorization_path, state
    )
    if (
        authorization["label"] != label
        or authorization["role"] != role
        or authorization["repetition"] != repetition
        or set(identities) != {"benchexec-launcher", "load-monitor"}
        or {identity["boot_id"] for identity in identities.values()}
        != {authorization["boot_id"]}
    ):
      raise RuntimeError("formal recovery authorization identity differs")
    expected_paths = {
        "definition": (
            root / authorization["files"]["definition"]["path"]
        ),
        "result": (
            root / authorization["files"]["result_directory"]
            / Path(paths["result"]).name
        ),
        "benchexec_log": (
            root / authorization["files"]["benchexec_log"]
        ),
        "benchexec_process": (
            root / f"provenance/{label}-benchexec.process.json"
        ),
        "process_descriptor": (
            root / authorization["files"]["process_descriptor"]["path"]
        ),
        "load_monitor": (
            root / authorization["files"]["load_monitor"]
        ),
        "monitor_pid": (
            root / f"provenance/{label}-load-monitor.jsonl.pid"
        ),
        "monitor_process": (
            root / f"provenance/{label}-load-monitor.jsonl.process.json"
        ),
        "machine_before": (
            root / authorization["files"]["machine_before"]
        ),
    }
    if any(
        Path(paths[name]).resolve() != expected
        for name, expected in expected_paths.items()
    ):
      raise RuntimeError("formal recovery authorization paths differ")
    result_tasks = result_task_names(paths["result"], state["manifest"])
    if not set(result_tasks) <= set(authorization["authorized_tasks"]):
      raise RuntimeError("formal recovery result exceeds authorization")
    return False
  selections = (
      (FROZEN_CAP16_ATHENA_V2_RECOVERY_SELECTION, True),
      (FROZEN_CAP16_ATHENA_ATTEMPT_2_V2_RECOVERY_SELECTION, False),
      (FROZEN_CAP16_ATHENA_ATTEMPT_3_V2_RECOVERY_SELECTION, False),
      (FROZEN_CAP16_ATHENA_ATTEMPT_4_V2_RECOVERY_SELECTION, False),
      (FROZEN_CAP16_ATHENA_ATTEMPT_5_V2_RECOVERY_SELECTION, False),
  )
  matches = [
      item for item in selections
      if (
          label == item[0]["label"]
          and role == item[0]["role"]
          and repetition == item[0]["repetition"]
      )
  ]
  if (
      len(matches) != 1
      or set(identities) != {"benchexec-launcher", "load-monitor"}
  ):
    raise RuntimeError(
        "formal recovery requires an exact frozen v2 selection"
    )
  selection, allow_final_log_only_completion = matches[0]
  for name, expected in selection["files"].items():
    path = Path(paths[name])
    expected_path = root / expected["path"]
    if (
        path != expected_path
        or path.is_symlink()
        or not path.is_file()
        or baseline.sha256_file(path) != expected["sha256"]
    ):
      raise RuntimeError("frozen v2 recovery selection differs")
  for relative, expected_hash in selection["closure_files"].items():
    path = root / relative
    if (
        path.is_symlink()
        or not path.is_file()
        or baseline.sha256_file(path) != expected_hash
    ):
      raise RuntimeError("frozen v2 recovery selection differs")
  result_directory = root / selection["result_directory"]
  if (
      result_directory.is_symlink()
      or not result_directory.is_dir()
  ):
    raise RuntimeError("frozen v2 recovery selection differs")
  result_entries = list(result_directory.rglob("*"))
  if any(
      path.is_symlink() or not (path.is_file() or path.is_dir())
      for path in result_entries
  ):
    raise RuntimeError("frozen v2 recovery selection differs")
  if (
      formal_result_directory_digest(result_directory)
      != selection["result_directory_digest"]
      or {
          path.relative_to(result_directory).as_posix()
          for path in result_entries
          if path.is_dir()
      }
      != set(selection["result_directories"])
  ):
    raise RuntimeError("frozen v2 recovery selection differs")
  captured = {identity["boot_id"] for identity in identities.values()}
  if captured != {selection["captured_boot_id"]}:
    raise RuntimeError("frozen v2 recovery boot identity differs")
  if read_boot_id() == selection["captured_boot_id"]:
    raise RuntimeError("frozen v2 recovery is not bound across reboot")
  return allow_final_log_only_completion


def marker_authorizes_final_log_only_completion(record):
  selection = FROZEN_CAP16_ATHENA_V2_RECOVERY_SELECTION
  if (
      record.get("schema_version") != FORMAL_ATTEMPT_SCHEMA
      or record.get("benchexec_exit") != 125
      or not record.get("result_incomplete")
      or record.get("label") != selection["label"]
      or record.get("role") != selection["role"]
      or record.get("repetition") != selection["repetition"]
      or not isinstance(record.get("files"), dict)
  ):
    return False
  return all(
      record["files"].get(name) == expected
      for name, expected in selection["files"].items()
  )


def frozen_attempt_5_final_log_only_pending(result, log, load_monitor):
  selection = FROZEN_CAP16_ATHENA_ATTEMPT_5_V2_RECOVERY_SELECTION
  selection_sha256 = sha256_text(
      json.dumps(selection, sort_keys=True, separators=(",", ":"))
  )
  if (
      selection_sha256
      != FROZEN_CAP16_ATHENA_ATTEMPT_5_V2_RECOVERY_SELECTION_SHA256
  ):
    raise RuntimeError("frozen attempt-5 recovery selector differs")
  return all(
      baseline.sha256_file(Path(actual))
      == selection["files"][name]["sha256"]
      for name, actual in (
          ("result", result),
          ("benchexec_log", log),
          ("load_monitor", load_monitor),
      )
  )


def validate_recovery_result(directory, expected_hash, rows, complete):
  candidates = sorted(Path(directory).glob("*.xml"))
  if len(candidates) != 1:
    raise RuntimeError("formal recovery result XML is not unique")
  result = candidates[0]
  if baseline.sha256_file(result) != expected_hash:
    raise RuntimeError("formal recovery result hash does not match")
  root = ET.parse(result).getroot()
  runs = root.findall("run")
  finished = sum(
      {"cputime", "memory", "status", "walltime"}.issubset({
          column.get("title") for column in run.findall("column")
      })
      for run in runs
  )
  if (
      root.get("error") != "incomplete"
      or len(runs) != rows
      or finished != complete
  ):
    raise RuntimeError("formal recovery result completion topology differs")
  return result


def recovery_selection_record(spec):
  return {
      "schema_version": FORMAL_RECOVERY_SELECTION_SCHEMA,
      "label": spec["label"],
      "selected_source": spec["source"],
      "quarantine": spec["quarantine"],
      "selected_result_sha256": spec["selected_result_sha256"],
      "displaced_result_sha256": spec["displaced_result_sha256"],
      "selected_complete_rows": spec["selected_complete_rows"],
      "displaced_complete_rows": spec["displaced_complete_rows"],
      "result_rows": spec["result_rows"],
      "selected_provenance": spec["selected_provenance"],
      "displaced_provenance": spec["displaced_provenance"],
  }


def validate_recovery_selection(root, spec):
  root = Path(root).resolve()
  selection = root / f"provenance/recovery-selections/{spec['label']}.json"
  expected = recovery_selection_record(spec)
  if json.loads(selection.read_text(encoding="utf-8")) != expected:
    raise RuntimeError("formal recovery selection ledger differs")
  source = root / spec["source"]
  quarantine = root / spec["quarantine"]
  if (
      baseline.sha256_file(source / "ABANDONED")
      != spec["abandoned_sha256"]
      or formal_result_directory_digest(
          root / f"results/{spec['label']}"
      ) != spec["selected_results_digest"]
      or formal_result_directory_digest(
          quarantine / "results"
      ) != spec["displaced_results_digest"]
  ):
    raise RuntimeError("formal recovery selection trees differ")
  validate_recovery_result(
      root / f"results/{spec['label']}",
      spec["selected_result_sha256"],
      spec["result_rows"],
      spec["selected_complete_rows"],
  )
  validate_recovery_result(
      quarantine / "results",
      spec["displaced_result_sha256"],
      spec["result_rows"],
      spec["displaced_complete_rows"],
  )
  for name in spec["selected_provenance"]:
    selected = root / "provenance" / name
    displaced = quarantine / "provenance" / name
    if (
        baseline.sha256_file(selected)
        != spec["selected_provenance"][name]
        or baseline.sha256_file(displaced)
        != spec["displaced_provenance"][name]
    ):
      raise RuntimeError("formal recovery selected provenance differs")
  return expected


def restore_formal_attempt(root, spec):
  root = Path(root).resolve()
  source = root / spec["source"]
  quarantine = root / spec["quarantine"]
  selection = root / f"provenance/recovery-selections/{spec['label']}.json"
  prepared = selection.with_suffix(".prepared.json")
  prepared_content = json.dumps({
      **recovery_selection_record(spec),
      "state": "prepared",
  }, indent=2, sort_keys=True) + "\n"
  if selection.exists():
    validate_recovery_selection(root, spec)
    if prepared.exists():
      if prepared.read_text(encoding="utf-8") != prepared_content:
        raise RuntimeError("formal recovery prepared ledger differs")
      prepared.unlink()
      descriptor = os.open(prepared.parent, os.O_RDONLY)
      try:
        os.fsync(descriptor)
      finally:
        os.close(descriptor)
    return selection
  selection.parent.mkdir(parents=True, exist_ok=True)
  if prepared.exists():
    if prepared.read_text(encoding="utf-8") != prepared_content:
      raise RuntimeError("formal recovery prepared ledger differs")
  else:
    canonical_results = root / f"results/{spec['label']}"
    selected_results = source / "results"
    if (
        baseline.sha256_file(source / "ABANDONED")
        != spec["abandoned_sha256"]
        or formal_result_directory_digest(selected_results)
        != spec["selected_results_digest"]
        or formal_result_directory_digest(canonical_results)
        != spec["displaced_results_digest"]
    ):
      raise RuntimeError("formal recovery source or displaced tree differs")
    validate_recovery_result(
        selected_results,
        spec["selected_result_sha256"],
        spec["result_rows"],
        spec["selected_complete_rows"],
    )
    validate_recovery_result(
        canonical_results,
        spec["displaced_result_sha256"],
        spec["result_rows"],
        spec["displaced_complete_rows"],
    )
    for name in spec["selected_provenance"]:
      if (
          baseline.sha256_file(source / "provenance" / name)
          != spec["selected_provenance"][name]
          or baseline.sha256_file(root / "provenance" / name)
          != spec["displaced_provenance"][name]
      ):
        raise RuntimeError("formal recovery provenance source differs")
    if quarantine.exists():
      raise RuntimeError("formal recovery quarantine already exists")
    quarantine.joinpath("provenance").mkdir(parents=True)
    write_recovery_evidence(prepared, prepared_content)

  def existing_with_hash(paths, expected, known, directory=False):
    matching = []
    for path in paths:
      if directory and path.is_dir():
        actual = formal_result_directory_digest(path)
      elif not directory and path.is_file() and not path.is_symlink():
        actual = baseline.sha256_file(path)
      else:
        continue
      if actual == expected:
        matching.append(path)
      elif actual not in known:
        raise RuntimeError(f"formal recovery transaction node differs: {path}")
    if len(matching) != 1:
      raise RuntimeError("formal recovery transaction is not exact-one")
    return matching[0]

  def move(source_path, destination_path):
    if source_path == destination_path:
      return
    if destination_path.exists():
      raise RuntimeError("formal recovery destination is occupied")
    os.replace(source_path, destination_path)
    for parent in {source_path.parent, destination_path.parent}:
      descriptor = os.open(parent, os.O_RDONLY)
      try:
        os.fsync(descriptor)
      finally:
        os.close(descriptor)

  canonical_results = root / f"results/{spec['label']}"
  selected_results = source / "results"
  displaced_results = quarantine / "results"
  selected_location = existing_with_hash(
      (selected_results, canonical_results, displaced_results),
      spec["selected_results_digest"],
      {
          spec["selected_results_digest"],
          spec["displaced_results_digest"],
      },
      directory=True,
  )
  displaced_location = existing_with_hash(
      (selected_results, canonical_results, displaced_results),
      spec["displaced_results_digest"],
      {
          spec["selected_results_digest"],
          spec["displaced_results_digest"],
      },
      directory=True,
  )
  if displaced_location != displaced_results:
    move(displaced_location, displaced_results)
  if selected_location != canonical_results:
    move(selected_location, canonical_results)
  for name in spec["selected_provenance"]:
    locations = (
        source / "provenance" / name,
        root / "provenance" / name,
        quarantine / "provenance" / name,
    )
    selected_location = existing_with_hash(
        locations,
        spec["selected_provenance"][name],
        {
            spec["selected_provenance"][name],
            spec["displaced_provenance"][name],
        },
    )
    displaced_location = existing_with_hash(
        locations,
        spec["displaced_provenance"][name],
        {
            spec["selected_provenance"][name],
            spec["displaced_provenance"][name],
        },
    )
    if displaced_location != quarantine / "provenance" / name:
      move(displaced_location, quarantine / "provenance" / name)
    if selected_location != root / "provenance" / name:
      move(selected_location, root / "provenance" / name)
  content = json.dumps(
      recovery_selection_record(spec), indent=2, sort_keys=True
  ) + "\n"
  write_recovery_evidence(selection, content)
  validate_recovery_selection(root, spec)
  prepared.unlink()
  descriptor = os.open(prepared.parent, os.O_RDONLY)
  try:
    os.fsync(descriptor)
  finally:
    os.close(descriptor)
  return selection


def command_restore_legacy_cap16_athena_attempt(args):
  selection = restore_formal_attempt(
      args.output_root, LEGACY_CAP16_ATHENA_REPETITION_1
  )
  print(selection)


def trusted_legacy_process_identity(root, label, path):
  if label != LEGACY_CAP16_ATHENA_REPETITION_1["label"]:
    raise RuntimeError("legacy process identity has no recovery selection")
  validate_recovery_selection(root, LEGACY_CAP16_ATHENA_REPETITION_1)
  path = Path(path).resolve()
  expected = (
      Path(root).resolve() / "provenance"
      / path.name
  )
  if path != expected:
    raise RuntimeError("legacy process identity path is not selected")
  try:
    return LEGACY_CAP16_ATHENA_REPETITION_1["selected_provenance"][
        path.name
    ]
  except KeyError as error:
    raise RuntimeError("legacy process identity is not selected") from error


def load_attempt_process_identity(
    path, root, label, trusted_legacy_sha256=None
):
  data = json.loads(Path(path).read_text(encoding="utf-8"))
  trusted = trusted_legacy_sha256
  if (
      data.get("schema_version") == LEGACY_FORMAL_PROCESS_IDENTITY_SCHEMA
      and trusted is None
  ):
    trusted = trusted_legacy_process_identity(root, label, path)
  return load_owned_process_identity(path, trusted)


def command_recover_formal_attempt(args):
  root = Path(args.output_root).resolve()
  inputs = {
      name: recovery_path(
          root, getattr(args, name), name.replace("_", " "), True
      )
      for name in (
          "definition",
          "result",
          "benchexec_log",
          "benchexec_process",
          "process_descriptor",
          "load_monitor",
          "monitor_pid",
          "monitor_process",
          "machine_before",
      )
  }
  outputs = {
      name: recovery_path(
          root, getattr(args, name), name.replace("_", " "), False
      )
      for name in (
          "monitor_stopped",
          "machine_after",
          "machine_check",
          "output",
      )
  }
  if len(set(inputs.values()) | set(outputs.values())) != (
      len(inputs) + len(outputs)
  ):
    raise RuntimeError("formal recovery evidence paths overlap")
  descriptor = load_formal_process_descriptor(
      inputs["process_descriptor"],
      root,
      args.mode,
      args.label,
      args.host,
  )
  identities = {}
  for role, name in (
      ("load-monitor", "monitor_process"),
      ("benchexec-launcher", "benchexec_process"),
  ):
    identity = load_attempt_process_identity(
        inputs[name], root, args.label
    )
    expected = {"role": role, **descriptor["identities"][role]}
    validate_formal_process_identity(identity, expected, require_unit=False)
    require_process_gone(
        identity,
        descriptor["systemd_unit"] if role == "benchexec-launcher" else None,
    )
    validate_formal_process_identity(identity, expected)
    identities[role] = identity
  validate_markerless_recovery_identity_selection(
      root,
      args.label,
      args.role,
      args.repetition,
      inputs,
      identities,
      args.sv_benchmarks,
  )
  canonical_label = (
      f"repetition-{args.repetition}"
      if args.role == "primary"
      else rf"repetition-{args.repetition}-replacement-attempt-[1-9]\d*"
  )
  if (
      args.label != canonical_label
      if args.role == "primary"
      else re.fullmatch(canonical_label, args.label) is None
  ):
    raise RuntimeError("formal recovery attempt label is not canonical")
  research_head = formal_recovery_research_head(
      root, args.research_provenance, args.mode
  )
  expected_outputs = formal_recovery_evidence_paths(
      root, args.label, research_head
  )
  for name, expected in expected_outputs.items():
    if outputs[name] != expected:
      raise RuntimeError(
          f"formal recovery {name.replace('_', ' ')} is not its "
          "versioned path"
      )
  complete_namespace = recovery_evidence_namespace_complete(expected_outputs)
  prepared_outputs = formal_recovery_preparation_paths(expected_outputs)
  if (
      complete_namespace
      and prepared_outputs["monitor_stopped"].parent.exists()
  ):
    raise RuntimeError(
        "formal recovery preparation conflicts with published evidence"
    )
  pid_text = inputs["monitor_pid"].read_text(encoding="utf-8")
  if not re.fullmatch(r"[1-9]\d*\n?", pid_text):
    raise RuntimeError("formal recovery monitor PID is invalid")
  pid = int(pid_text)
  monitor_identity = load_attempt_process_identity(
      inputs["monitor_process"], root, args.label
  )
  if monitor_identity["pid"] != pid:
    raise RuntimeError("formal recovery monitor PID does not match its identity")
  monitor_lines = formal_monitor_lines(
      inputs["load_monitor"], allow_trailing_nul=True
  )
  load_formal_contention_intervals(
      inputs["load_monitor"], allow_trailing_nul=True
  )
  samples = len(monitor_lines) - 1
  if samples <= 0:
    raise RuntimeError("formal recovery load monitor has no samples")
  stop_content = (
      f"pid={pid}\nexit=unobserved\nsamples={samples}\n"
      "recovery=authenticated-process-gone\n"
  )
  if complete_namespace:
    validate_stored_recovery_evidence(
        outputs, inputs["machine_before"], identities, stop_content
    )
  elif recovery_preparation_complete(prepared_outputs):
    validate_stored_recovery_evidence(
        prepared_outputs,
        inputs["machine_before"],
        identities,
        stop_content,
    )
    publish_recovery_preparation(prepared_outputs, outputs)
  else:
    discard_incomplete_recovery_preparation(prepared_outputs)
    prepared_outputs["monitor_stopped"].parent.mkdir(parents=True)
    write_recovery_evidence(
        prepared_outputs["monitor_stopped"], stop_content
    )
    temporary = prepared_outputs["machine_after"].with_name(
        f".{prepared_outputs['machine_after'].name}.capture-{os.getpid()}"
    )
    try:
      baseline.command_machine(argparse.Namespace(output=str(temporary)))
      write_recovery_evidence(
          prepared_outputs["machine_after"],
          temporary.read_text(encoding="utf-8"),
      )
    finally:
      temporary.unlink(missing_ok=True)
    check = recovered_machine_check_record(
        inputs["machine_before"],
        prepared_outputs["machine_after"],
        recovery_process_boot_binding(identities),
    )
    write_recovery_evidence(
        prepared_outputs["machine_check"],
        json.dumps(check, sort_keys=True) + "\n",
    )
    validate_stored_recovery_evidence(
        prepared_outputs,
        inputs["machine_before"],
        identities,
        stop_content,
    )
    publish_recovery_preparation(prepared_outputs, outputs)
  recovered_args = argparse.Namespace(**vars(args))
  recovered_args.benchexec_exit = 125
  command_formal_attempt_complete(recovered_args)


def validate_formal_closure(args):
  root = Path(args.output_root).resolve()
  manifest_path = Path(args.manifest).resolve()
  validate_manifest(manifest_path, args.sv_benchmarks)
  manifest = baseline.load_task_manifest(manifest_path)
  if len(args.repetition_plan) != 2:
    raise RuntimeError("formal closure requires exactly two repetition plans")
  plan_schemas = [
      json.loads(Path(plan).read_text(encoding="utf-8")).get(
          "schema_version"
      )
      for plan in args.repetition_plan
  ]
  generic_recovery = plan_schemas == [FORMAL_RECOVERY_PLAN_SCHEMA] * 2
  if (
      FORMAL_RECOVERY_PLAN_SCHEMA in plan_schemas
      and not generic_recovery
  ):
    raise RuntimeError("formal recovery and legacy plans cannot be mixed")
  complete = root / "summary/.complete"
  if args.require_complete:
    if (
        complete.is_symlink()
        or not complete.is_file()
        or complete.read_text(encoding="utf-8") != "complete\n"
    ):
      raise RuntimeError("formal output completion sentinel is invalid")
  elif complete.exists():
    raise RuntimeError("formal output completed before closure validation")
  expected_summary = {
      "classification.csv",
      "hard-portfolio.csv",
      "mixed.csv",
      "row-provenance.json",
      "summary.json",
      "verifier-failure-quarantine.csv",
      "wrong-quarantine.csv",
  }
  actual_summary = {
      path.name
      for path in (root / "summary").iterdir()
      if path.name != ".complete"
  }
  if actual_summary != expected_summary:
    raise RuntimeError("formal summary topology is incomplete")
  artifact = root / "provenance/artifact-manifest.json"
  validate_artifact_manifest(
      root, artifact, {"summary/.complete"}
  )
  mandatory = [
      "input/research/inventory.sha256",
      "provenance/build.log",
      "provenance/cgroup-check.log",
      "provenance/machine-preflight-start.json",
      "provenance/machine-preflight-end.json",
      "provenance/machine-preflight-check.json",
      "provenance/research-verification-final.log",
      "provenance/runtime-verification-final.log",
      "provenance/runtime-closure.txt",
  ]
  for relative in mandatory:
    if not (root / relative).is_file():
      raise RuntimeError(f"formal closure lacks mandatory file: {relative}")
  marker_records = {}
  marker_dir = root / "provenance/attempts"
  markers = (
      [] if generic_recovery else sorted(marker_dir.glob("*.json"))
  )
  if not markers and not generic_recovery:
    raise RuntimeError("formal closure has no attempt markers")
  for marker in markers:
    record = validate_formal_attempt_marker(
        marker,
        root,
        Path(args.manifest).resolve(),
        args.sv_benchmarks,
        args.host,
        args.mode,
    )
    marker_records[record["label"]] = record
  expected_attempts = {}
  repetitions = []
  authenticated_plans = []
  for repetition, plan_value in enumerate(args.repetition_plan, start=1):
    plan_path = Path(plan_value).resolve()
    try:
      plan_path.relative_to(root)
    except ValueError as error:
      raise RuntimeError("formal closure repetition plan escapes output") from error
    if not plan_path.is_file() or plan_path.is_symlink():
      raise RuntimeError("formal closure repetition plan is not regular")
    if generic_recovery:
      authenticated = load_formal_recovery_plan(
          plan_path, args.sv_benchmarks
      )
    elif args.mode == "cap16":
      authenticated = load_screen_plan(
          plan_path,
          manifest,
          manifest_path,
          args.host,
          args.sv_benchmarks,
          args.benchmark_definition,
          plan_schema=CAP16_FORMAL_REPETITION_PLAN_SCHEMA,
          repetition=repetition,
          display=FORMAL_DISPLAY,
          time_limit="900 s",
          taint_schema=FORMAL_TAINT_SCHEMA,
          definition_validator=validate_formal_definition,
          hard_threshold=200,
      )
    else:
      authenticated = load_repetition_plan(
          plan_path,
          manifest,
          manifest_path,
          args.host,
          args.sv_benchmarks,
          args.benchmark_definition,
          200,
      )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    authenticated_plans.append(authenticated)
    repetitions.append(plan["repetition"])
    if generic_recovery:
      continue
    primary_label = f"repetition-{plan['repetition']}"
    expected_attempts[primary_label] = {
        "repetition": plan["repetition"],
        "role": "primary",
        "result_sha256": plan["primary"]["sha256"],
        "definition_sha256": baseline.sha256_file(
            Path(args.benchmark_definition)
        ),
        "tasks": sorted(manifest),
    }
    for entry in plan["replacements"]:
      label = Path(entry["path"]).parent.name
      expected_attempts[label] = {
          "repetition": plan["repetition"],
          "role": "replacement",
          "result_sha256": entry["sha256"],
          "definition_sha256": entry["definition_sha256"],
          "tasks": entry.get("result_tasks", entry.get("tasks")),
      }
  if repetitions != [1, 2]:
    raise RuntimeError("formal closure plans must be ordered 1 then 2")
  if len({plan["plan_sha256"] for plan in authenticated_plans}) != 2:
    raise RuntimeError("formal closure repetition plans are not distinct")
  authenticated_results = [
      digest
      for plan in authenticated_plans
      for digest in [
          plan["primary_sha256"],
          *plan["replacement_sha256"],
      ]
  ]
  if len(authenticated_results) != len(set(authenticated_results)):
    raise RuntimeError("formal closure result artifacts are reused")
  if (
      not generic_recovery
      and {marker.stem for marker in markers} != set(expected_attempts)
  ):
    raise RuntimeError(
        "formal attempt markers do not match exactly the planned attempts"
    )
  for label, expected in expected_attempts.items():
    record = marker_records[label]
    actual = {
        "repetition": record["repetition"],
        "role": record["role"],
        "result_sha256": record["files"]["result"]["sha256"],
        "definition_sha256": record["files"]["definition"]["sha256"],
        "tasks": record["result_tasks"],
    }
    if actual != expected:
      raise RuntimeError(
          f"formal attempt marker does not match its planned attempt: {label}"
      )
  return {
      "artifact_aggregate_sha256": json.loads(
          artifact.read_text(encoding="utf-8")
      )["aggregate_sha256"],
      "attempt_count": len(markers),
      "complete": args.require_complete,
      "valid": True,
  }


def command_validate_formal_closure(args):
  print(json.dumps(validate_formal_closure(args), sort_keys=True))


def validate_sha256_inventory(root, inventory_path, expected_paths=None):
  root = Path(root).resolve()
  inventory_path = Path(inventory_path).resolve()
  if (
      inventory_path.is_symlink()
      or not inventory_path.is_file()
      or inventory_path.parent != root
  ):
    raise RuntimeError("SHA-256 inventory is not a regular root file")
  entries = {}
  for line in inventory_path.read_text(encoding="utf-8").splitlines():
    match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
    if match is None:
      raise RuntimeError("SHA-256 inventory line is invalid")
    digest, relative_text = match.groups()
    relative = Path(relative_text)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() in entries
    ):
      raise RuntimeError("SHA-256 inventory path is invalid")
    path = root / relative
    current = root
    symlink_ancestor = False
    for component in relative.parts[:-1]:
      current /= component
      if current.is_symlink():
        symlink_ancestor = True
        break
    if (
        symlink_ancestor
        or path.is_symlink()
        or not path.is_file()
        or baseline.sha256_file(path) != digest
    ):
      raise RuntimeError(f"SHA-256 inventory mismatch: {relative}")
    entries[relative.as_posix()] = digest
  if list(entries) != sorted(entries):
    raise RuntimeError("SHA-256 inventory paths are not sorted")
  if expected_paths is not None and set(entries) != set(expected_paths):
    raise RuntimeError("SHA-256 inventory topology is not exact")
  return entries


def cap8_formal_probe_paths(formal_output):
  root = Path(formal_output).resolve()
  evidence = root / "input/evidence"
  research = root / "input/research"
  return {
      "root": root,
      "manifest": (
          root / "input/formal/candidate-manifest-valkyrie-formal.json"
      ),
      "formal_package_artifact": root / "input/formal/artifact-manifest.json",
      "definition": root / "generated/hard-case-candidates.xml",
      "plan_1": root / "repetition-1-plan.json",
      "plan_2": root / "repetition-2-plan.json",
      "hard": root / "summary/hard-portfolio.csv",
      "classification": root / "summary/classification.csv",
      "summary": root / "summary/summary.json",
      "artifact": root / "provenance/artifact-manifest.json",
      "evidence": evidence,
      "research": research,
      "saved_dataset": research / "scripts/dataset.py",
      "research_head": research / "research-head.txt",
      "research_inventory": research / "inventory.sha256",
  }


def frozen_cap8_formal_artifact_aggregate():
  frozen = FROZEN_CAP8_FORMAL_ARTIFACT_AGGREGATE_SHA256
  if re.fullmatch(r"[0-9a-f]{64}", frozen) is None:
    raise RuntimeError("cap-8 r8 formal artifact aggregate pin is pending")
  return frozen


def cap8_phase_result(evidence, role):
  matches = [
      path for path in (
          evidence / f"{role}-result.xml",
          evidence / f"{role}-result.xml.bz2",
      )
      if path.is_file() and not path.is_symlink()
  ]
  if len(matches) != 1:
    raise RuntimeError(f"cap-8 r8 {role} Phase-A result is not unique")
  return matches[0]


def cap8_summary_reproduction_arguments(paths, sv_benchmarks, output_dir):
  evidence = paths["evidence"]
  arguments = [
      "summarize",
      "--parent-manifest", str(evidence / "parent-manifest.json"),
  ]
  for role in ("original", "reroute", "recovery"):
    arguments.extend([
        "--phase-a-manifest", str(evidence / f"{role}-manifest.json"),
    ])
  for role in ("original", "reroute", "recovery"):
    arguments.extend([
        "--phase-a-result", str(cap8_phase_result(evidence, role)),
    ])
  for role in ("original", "reroute", "recovery"):
    arguments.extend([
        "--survivor-manifest", str(evidence / f"{role}-survivor.json"),
    ])
  arguments.extend([
      "--sv-benchmarks", str(Path(sv_benchmarks).resolve()),
      "--manifest", str(paths["manifest"]),
      "--benchmark-definition", str(paths["definition"]),
      "--repetition-plan", str(paths["plan_1"]),
      "--repetition-plan", str(paths["plan_2"]),
      "--output-dir", str(Path(output_dir).resolve()),
      "--hard-threshold", "200",
  ])
  return arguments


def run_saved_dataset(script, arguments, python_bin=None):
  if python_bin is None:
    python_bin = sys.executable
  script = Path(script).resolve()
  for path in script.parent.rglob("*"):
    if (
        path.is_file()
        and path.suffix in {".pyc", ".pyo"}
        and "__pycache__" not in path.relative_to(script.parent).parts
    ):
      raise RuntimeError(
          f"sourceless Python bytecode could shadow pinned source: {path}"
      )
  command = [
      str(python_bin),
      *PYTHON_RUNTIME_FLAGS,
      "-c",
      (
          "import runpy,sys;"
          "from pathlib import Path;"
          "script=Path(sys.argv.pop(1)).resolve();"
          "sys.argv[0]=str(script);"
          "sys.path.insert(0,str(script.parent));"
          "runpy.run_path(str(script),run_name='__main__')"
      ),
      str(script),
      *arguments,
  ]
  subprocess.run(command, check=True)


def authenticate_cap8_formal_for_probe(formal_output, sv_benchmarks):
  frozen_aggregate = frozen_cap8_formal_artifact_aggregate()
  paths = cap8_formal_probe_paths(formal_output)
  declared = Path(formal_output)
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != paths["root"]
      or not paths["root"].is_dir()
  ):
    raise RuntimeError("cap-8 r8 formal output must be a regular directory")
  package_artifact = validate_artifact_manifest(
      paths["manifest"].parent,
      paths["formal_package_artifact"],
      set(),
      expected_root=".",
  )
  if (
      baseline.sha256_file(paths["formal_package_artifact"])
      != FROZEN_CAP8_FORMAL_PACKAGE_MANIFEST_SHA256
      or package_artifact["aggregate_sha256"]
      != FROZEN_CAP8_FORMAL_PACKAGE_AGGREGATE_SHA256
      or baseline.sha256_file(paths["manifest"])
      != FROZEN_FORMAL_MANIFEST_SHA256
  ):
    raise RuntimeError("cap-8 r8 frozen formal input package is invalid")
  manifest = validate_manifest(paths["manifest"], sv_benchmarks)
  if (
      manifest["task_count"] != FROZEN_CAP8_FORMAL_TASK_COUNT
      or any(row["source"] != "sv-benchmarks" for row in manifest["tasks"])
  ):
    raise RuntimeError("cap-8 r8 formal manifest identity is invalid")

  evidence_paths = {
      "corpus/properties/unreach-call.prp",
      "parent-manifest.json",
      *(
          f"{role}-{kind}.{suffix}"
          for role in ("original", "reroute", "recovery")
          for kind, suffix in (
              ("manifest", "json"),
              ("survivor", "json"),
          )
      ),
  }
  for role in ("original", "reroute", "recovery"):
    evidence_paths.add(
        cap8_phase_result(paths["evidence"], role)
        .relative_to(paths["evidence"]).as_posix()
    )
  validate_sha256_inventory(
      paths["evidence"],
      paths["evidence"] / "inventory.sha256",
      evidence_paths,
  )

  research_paths = {
      "research-diff.patch",
      "research-head.txt",
      "research-index-flags.txt",
      "research-state.json",
      "research-status.porcelain",
      "scripts/baseline.py",
      "scripts/dataset.py",
      "scripts/run-stock-formal-dataset.sh",
  }
  if (
      paths["research_head"].read_text(encoding="utf-8")
      != f"{FROZEN_CAP8_RESEARCH_HEAD}\n"
      or baseline.sha256_file(paths["research_inventory"])
      != FROZEN_CAP8_RESEARCH_INVENTORY_SHA256
  ):
    raise RuntimeError("cap-8 r8 saved research identity is invalid")
  validate_sha256_inventory(
      paths["research"], paths["research_inventory"], research_paths
  )

  mandatory = (
      "provenance/build.log",
      "provenance/cgroup-check.log",
      "provenance/machine-preflight-start.json",
      "provenance/machine-preflight-end.json",
      "provenance/machine-preflight-check.json",
      "provenance/research-verification-final.log",
      "provenance/runtime-verification-final.log",
      "provenance/runtime-closure.txt",
  )
  for relative in mandatory:
    path = paths["root"] / relative
    if path.is_symlink() or not path.is_file():
      raise RuntimeError(
          f"cap-8 r8 formal closure lacks evidence: {relative}"
      )
  failure_evidence = [
      path for path in (paths["root"] / "provenance").iterdir()
      if "failure" in path.name
  ]
  if failure_evidence:
    raise RuntimeError("cap-8 r8 formal launcher did not close successfully")
  runtime_closure = {}
  for line in (
      paths["root"] / "provenance/runtime-closure.txt"
  ).read_text(encoding="utf-8").splitlines():
    if "=" not in line:
      raise RuntimeError("cap-8 r8 runtime closure line is invalid")
    key, value = line.split("=", 1)
    if key in runtime_closure:
      raise RuntimeError("cap-8 r8 runtime closure key is duplicated")
    runtime_closure[key] = value
  if runtime_closure != FROZEN_CAP8_RUNTIME_CLOSURE:
    raise RuntimeError("cap-8 r8 runtime closure is not the frozen runtime")
  expected_summary = {
      "classification.csv",
      "hard-portfolio.csv",
      "mixed.csv",
      "row-provenance.json",
      "summary.json",
      "verifier-failure-quarantine.csv",
      "wrong-quarantine.csv",
  }
  if (
      {
          path.name for path in (paths["root"] / "summary").iterdir()
      }
      != expected_summary
  ):
    raise RuntimeError("cap-8 r8 summary topology is not exact")
  for plan in (paths["plan_1"], paths["plan_2"]):
    if plan.is_symlink() or not plan.is_file():
      raise RuntimeError("cap-8 r8 repetition plan is not regular")

  with tempfile.TemporaryDirectory(
      prefix="vguide-cap8-r8-summary-check."
  ) as temporary:
    run_saved_dataset(
        paths["saved_dataset"],
        cap8_summary_reproduction_arguments(
            paths, sv_benchmarks, temporary
        ),
        python_bin="/usr/bin/python3.10",
    )
    reproduced = Path(temporary)
    if {path.name for path in reproduced.iterdir()} != expected_summary:
      raise RuntimeError("cap-8 r8 reproduced summary topology is not exact")
    for name in expected_summary:
      if (
          (reproduced / name).read_bytes()
          != (paths["root"] / "summary" / name).read_bytes()
      ):
        raise RuntimeError("cap-8 r8 summary does not reproduce byte-identically")

  artifact = validate_artifact_manifest(
      paths["root"], paths["artifact"], set()
  )
  if artifact["aggregate_sha256"] != frozen_aggregate:
    raise RuntimeError("cap-8 r8 formal artifact aggregate is not frozen")
  with paths["classification"].open(newline="", encoding="utf-8") as source:
    classification = list(csv.DictReader(source))
  with paths["hard"].open(newline="", encoding="utf-8") as source:
    hard = list(csv.DictReader(source))
  expected = [
      row for row in classification
      if row.get("classification")
      in {"stable_hard_solved", "stable_unsolved"}
  ]
  tasks = [row.get("task") for row in hard]
  details = {row["task"]: row for row in manifest["tasks"]}
  if (
      hard != expected
      or not hard
      or tasks != sorted(tasks)
      or len(tasks) != len(set(tasks))
      or any(task not in details for task in tasks)
  ):
    raise RuntimeError(
        "cap-8 r8 hard portfolio is not the exact authenticated stable-hard set"
    )
  return paths, manifest, hard, {
      "artifact_aggregate_sha256": artifact["aggregate_sha256"],
      "valid": True,
  }


def command_authenticate_cap8_formal_for_probe(args):
  _, manifest, hard, closure = authenticate_cap8_formal_for_probe(
      args.formal_output, args.sv_benchmarks
  )
  print(json.dumps({
      "artifact_aggregate_sha256": closure[
          "artifact_aggregate_sha256"
      ],
      "hard_task_count": len(hard),
      "manifest_task_count": manifest["task_count"],
      "valid": True,
  }, sort_keys=True))


def cap16_formal_probe_paths(formal_output):
  root = Path(formal_output).resolve()
  phase_a = root / "input/evidence"
  return {
      "root": root,
      "phase_a": phase_a,
      "saved_dataset": root / "input/research/scripts/dataset.py",
      "manifest": (
          root
          / "input/evidence/summary/candidate-manifest-analysis-survivors.json"
      ),
      "definition": root / "generated/hard-case-candidates.xml",
      "plan_1": root / "repetition-1-plan.json",
      "plan_2": root / "repetition-2-plan.json",
      "hard": root / "summary/hard-portfolio.csv",
      "classification": root / "summary/classification.csv",
      "summary": root / "summary/summary.json",
      "artifact": root / "provenance/artifact-manifest.json",
  }


def frozen_cap16_formal_artifact_aggregate():
  frozen = FROZEN_CAP16_FORMAL_ARTIFACT_AGGREGATE_SHA256
  if re.fullmatch(r"[0-9a-f]{64}", frozen) is None:
    raise RuntimeError(
        "cap-16 formal artifact aggregate pin is pending"
    )
  return frozen


def authenticate_cap16_formal_for_probe(formal_output, sv_benchmarks):
  frozen_aggregate = frozen_cap16_formal_artifact_aggregate()
  paths = cap16_formal_probe_paths(formal_output)
  declared = Path(formal_output)
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != paths["root"]
      or not paths["root"].is_dir()
  ):
    raise RuntimeError("cap-16 formal output must be a regular directory")
  artifact = validate_artifact_manifest(
      paths["root"], paths["artifact"], {"summary/.complete"}
  )
  if artifact["aggregate_sha256"] != frozen_aggregate:
    raise RuntimeError("cap-16 formal artifact aggregate is not frozen")
  with tempfile.TemporaryDirectory(
      prefix="vguide-cap16-formal-summary-check."
  ) as temporary:
    run_saved_dataset(paths["saved_dataset"], [
        "summarize-cap16-formal",
        "--phase-a-output", str(paths["phase_a"]),
        "--sv-benchmarks", str(Path(sv_benchmarks).resolve()),
        "--manifest", str(paths["manifest"]),
        "--benchmark-definition", str(paths["definition"]),
        "--repetition-plan", str(paths["plan_1"]),
        "--repetition-plan", str(paths["plan_2"]),
        "--output-dir", str(Path(temporary).resolve()),
        "--hard-threshold", "200",
    ], python_bin="/usr/bin/python3.12")
    reproduced = Path(temporary)
    actual_summary = {
        path.name for path in (paths["root"] / "summary").iterdir()
        if path.name != ".complete"
    }
    if {path.name for path in reproduced.iterdir()} != actual_summary:
      raise RuntimeError("cap-16 formal summary topology does not reproduce")
    for candidate in reproduced.iterdir():
      if (
          candidate.read_bytes()
          != (paths["root"] / "summary" / candidate.name).read_bytes()
      ):
        raise RuntimeError("cap-16 formal summary does not reproduce exactly")
  closure = validate_formal_closure(
      argparse.Namespace(
          output_root=str(paths["root"]),
          manifest=str(paths["manifest"]),
          benchmark_definition=str(paths["definition"]),
          sv_benchmarks=str(Path(sv_benchmarks).resolve()),
          host="athena",
          mode="cap16",
          repetition_plan=[str(paths["plan_1"]), str(paths["plan_2"])],
          require_complete=True,
      )
  )
  if (
      closure["artifact_aggregate_sha256"]
      != frozen_aggregate
  ):
    raise RuntimeError("cap-16 formal artifact aggregate is not frozen")
  manifest = validate_manifest(paths["manifest"], sv_benchmarks)
  with paths["classification"].open(newline="", encoding="utf-8") as source:
    classification = list(csv.DictReader(source))
  with paths["hard"].open(newline="", encoding="utf-8") as source:
    hard = list(csv.DictReader(source))
  expected = [
      row
      for row in classification
      if row.get("classification")
      in {"stable_hard_solved", "stable_analysis_unsolved"}
  ]
  tasks = [row.get("task") for row in hard]
  details = {row["task"]: row for row in manifest["tasks"]}
  if (
      hard != expected
      or not hard
      or tasks != sorted(tasks)
      or len(tasks) != len(set(tasks))
      or any(task not in details for task in tasks)
      or any(details[task]["source"] != "sv-benchmarks" for task in tasks)
  ):
    raise RuntimeError(
        "cap-16 formal hard portfolio is not the exact authenticated stable-hard set"
    )
  return paths, manifest, hard, closure


def command_authenticate_cap16_formal_for_probe(args):
  _, manifest, hard, closure = authenticate_cap16_formal_for_probe(
      args.formal_output, args.sv_benchmarks
  )
  print(json.dumps({
      "artifact_aggregate_sha256": closure[
          "artifact_aggregate_sha256"
      ],
      "hard_task_count": len(hard),
      "manifest_task_count": manifest["task_count"],
      "valid": True,
  }, sort_keys=True))


def package_strict_probe_input(args, cohort):
  profile = strict_probe_profile(cohort)
  authenticate = (
      authenticate_cap8_formal_for_probe
      if cohort == "cap8"
      else authenticate_cap16_formal_for_probe
  )
  paths, manifest, hard, closure = authenticate(
      args.formal_output, args.sv_benchmarks
  )
  output = Path(args.output_dir).resolve()
  require_absent_or_empty_output(output)
  output.mkdir(parents=True, exist_ok=True)
  tasks = [row["task"] for row in hard]
  source_manifest_sha256 = baseline.sha256_file(paths["manifest"])
  hard_sha256 = baseline.sha256_file(paths["hard"])
  derived = manifest_subset(
      manifest,
      tasks,
      {
          "operation": profile["operation"],
          "source_manifest_sha256": source_manifest_sha256,
          "source_formal_manifest_sha256": source_manifest_sha256,
          "source_formal_hard_portfolio_sha256": hard_sha256,
          "source_formal_artifact_aggregate_sha256": closure[
              "artifact_aggregate_sha256"
          ],
          "selection_independent_of_augmented_outcomes": True,
      },
  )
  if (paths["manifest"].parent / "corpus").is_dir():
    shutil.copytree(paths["manifest"].parent / "corpus", output / "corpus")
  manifest_path = output / profile["manifest_name"]
  manifest_path.write_text(
      json.dumps(derived, indent=2) + "\n", encoding="utf-8"
  )
  shutil.copyfile(paths["hard"], output / "hard-portfolio.csv")
  for source, target in (
      (paths["manifest"], "source-formal-manifest.json"),
      (paths["classification"], "source-formal-classification.csv"),
      (paths["summary"], "source-formal-summary.json"),
      (paths["artifact"], "source-formal-artifact-manifest.json"),
  ):
    shutil.copyfile(source, output / target)
  identity = {
      "schema_version": profile["input_schema"],
      "host": profile["host"],
      "task_count": len(tasks),
      "formal_artifact_aggregate_sha256": closure[
          "artifact_aggregate_sha256"
      ],
      "formal_artifact_manifest_sha256": baseline.sha256_file(
          paths["artifact"]
      ),
      "formal_manifest_sha256": source_manifest_sha256,
      "formal_hard_portfolio_sha256": hard_sha256,
      "formal_classification_sha256": baseline.sha256_file(
          paths["classification"]
      ),
      "formal_summary_sha256": baseline.sha256_file(paths["summary"]),
      "probe_manifest_sha256": baseline.sha256_file(manifest_path),
      "selection_independent_of_augmented_outcomes": True,
  }
  (output / "identity.json").write_text(
      json.dumps(identity, indent=2) + "\n", encoding="utf-8"
  )
  validate_strict_probe_input(output, args.sv_benchmarks, cohort)
  print(json.dumps(identity, sort_keys=True))


def command_package_cap8_probe_input(args):
  package_strict_probe_input(args, "cap8")


def command_package_cap16_probe_input(args):
  package_strict_probe_input(args, "cap16")


def validate_strict_probe_input(probe_input, sv_benchmarks, cohort):
  profile = strict_probe_profile(cohort)
  root = Path(probe_input).resolve()
  identity_path = root / "identity.json"
  manifest_path = root / profile["manifest_name"]
  hard_path = root / "hard-portfolio.csv"
  identity = json.loads(identity_path.read_text(encoding="utf-8"))
  if (
      not isinstance(identity, dict)
      or set(identity)
      != {
          "schema_version",
          "host",
          "task_count",
          "formal_artifact_aggregate_sha256",
          "formal_artifact_manifest_sha256",
          "formal_manifest_sha256",
          "formal_hard_portfolio_sha256",
          "formal_classification_sha256",
          "formal_summary_sha256",
          "probe_manifest_sha256",
          "selection_independent_of_augmented_outcomes",
      }
      or identity["schema_version"] != profile["input_schema"]
      or identity["host"] != profile["host"]
      or identity["selection_independent_of_augmented_outcomes"] is not True
      or any(
          re.fullmatch(r"[0-9a-f]{64}", identity[name]) is None
          for name in identity
          if name.startswith("formal_") or name == "probe_manifest_sha256"
      )
      or identity["probe_manifest_sha256"]
      != baseline.sha256_file(manifest_path)
  ):
    raise RuntimeError(f"{cohort} probe input identity is invalid")
  manifest = validate_manifest(manifest_path, sv_benchmarks)
  source_manifest_path = root / "source-formal-manifest.json"
  source_classification_path = root / "source-formal-classification.csv"
  source_summary_path = root / "source-formal-summary.json"
  source_artifact_path = root / "source-formal-artifact-manifest.json"
  source_manifest = validate_manifest(
      source_manifest_path, sv_benchmarks
  )
  artifact = json.loads(
      source_artifact_path.read_text(encoding="utf-8")
  )
  artifact_index = validate_artifact_manifest_index(artifact)
  if not Path(artifact["root"]).is_absolute():
    raise RuntimeError(f"{cohort} probe formal artifact root is not absolute")
  formal_paths = (
      cap8_formal_probe_paths(Path(artifact["root"]))
      if cohort == "cap8"
      else cap16_formal_probe_paths(Path(artifact["root"]))
  )
  expected_artifacts = {
      formal_paths["manifest"].relative_to(formal_paths["root"]).as_posix():
          identity["formal_manifest_sha256"],
      formal_paths["classification"].relative_to(
          formal_paths["root"]
      ).as_posix(): identity["formal_classification_sha256"],
      formal_paths["hard"].relative_to(formal_paths["root"]).as_posix():
          identity["formal_hard_portfolio_sha256"],
      formal_paths["summary"].relative_to(formal_paths["root"]).as_posix():
          identity["formal_summary_sha256"],
  }
  if (
      identity["formal_artifact_manifest_sha256"]
      != baseline.sha256_file(source_artifact_path)
      or identity["formal_manifest_sha256"]
      != (
          FROZEN_FORMAL_MANIFEST_SHA256
          if cohort == "cap8"
          else FROZEN_CAP16_PHASE_A_SURVIVOR_SHA256
      )
      or identity["formal_artifact_aggregate_sha256"]
      != artifact["aggregate_sha256"]
      or identity["formal_artifact_aggregate_sha256"]
      != (
          frozen_cap8_formal_artifact_aggregate()
          if cohort == "cap8"
          else frozen_cap16_formal_artifact_aggregate()
      )
      or any(
          relative not in artifact_index
          or artifact_index[relative]["sha256"] != digest
          for relative, digest in expected_artifacts.items()
      )
      or identity["formal_manifest_sha256"]
      != baseline.sha256_file(source_manifest_path)
      or identity["formal_classification_sha256"]
      != baseline.sha256_file(source_classification_path)
      or identity["formal_summary_sha256"]
      != baseline.sha256_file(source_summary_path)
  ):
    raise RuntimeError(f"{cohort} probe formal-closure backlink is invalid")
  with hard_path.open(newline="", encoding="utf-8") as source:
    hard = list(csv.DictReader(source))
  with source_classification_path.open(
      newline="", encoding="utf-8"
  ) as source:
    classification = list(csv.DictReader(source))
  tasks = [row.get("task") for row in hard]
  task_basenames = [
      Path(row["task_path"]).name for row in manifest["tasks"]
  ]
  source_by_task = {
      row["task"]: row for row in source_manifest["tasks"]
  }
  if (
      not hard
      or tasks != sorted(tasks)
      or len(tasks) != len(set(tasks))
      or tasks != sorted(row["task"] for row in manifest["tasks"])
      or len(task_basenames) != len(set(task_basenames))
      or identity["task_count"] != len(tasks)
      or identity["formal_hard_portfolio_sha256"]
      != baseline.sha256_file(hard_path)
      or hard
      != [
          row for row in classification
          if row.get("classification")
          in profile["accepted_labels"]
      ]
      or manifest["derivation"] != {
          "operation": profile["operation"],
          "source_manifest_sha256": identity["formal_manifest_sha256"],
          "source_formal_manifest_sha256":
              identity["formal_manifest_sha256"],
          "source_formal_hard_portfolio_sha256":
              identity["formal_hard_portfolio_sha256"],
          "source_formal_artifact_aggregate_sha256":
              identity["formal_artifact_aggregate_sha256"],
          "selection_independent_of_augmented_outcomes": True,
      }
      or any(
          source_by_task.get(row["task"]) != row
          for row in manifest["tasks"]
      )
  ):
    raise RuntimeError(f"{cohort} probe input hard portfolio is invalid")
  return root, manifest_path, manifest, hard, identity


def validate_cap8_probe_input(probe_input, sv_benchmarks):
  return validate_strict_probe_input(probe_input, sv_benchmarks, "cap8")


def validate_cap16_probe_input(probe_input, sv_benchmarks):
  return validate_strict_probe_input(probe_input, sv_benchmarks, "cap16")


def command_validate_cap8_probe_input(args):
  _, _, manifest, _, identity = validate_cap8_probe_input(
      args.probe_input, args.sv_benchmarks
  )
  print(json.dumps({
      "task_count": manifest["task_count"],
      "formal_artifact_aggregate_sha256": identity[
          "formal_artifact_aggregate_sha256"
      ],
      "valid": True,
  }, sort_keys=True))


def command_validate_cap16_probe_input(args):
  _, _, manifest, _, identity = validate_cap16_probe_input(
      args.probe_input, args.sv_benchmarks
  )
  print(json.dumps({
      "task_count": manifest["task_count"],
      "formal_artifact_aggregate_sha256": identity[
          "formal_artifact_aggregate_sha256"
      ],
      "valid": True,
  }, sort_keys=True))


def validate_strict_probe_closure(args, cohort):
  profile = strict_probe_profile(cohort)
  root = Path(args.output_root).resolve()
  probe_input = root / "input/formal"
  _, manifest_path, _, _, _ = validate_strict_probe_input(
      probe_input, args.sv_benchmarks, cohort
  )
  complete = root / "summary/.complete"
  if args.require_complete:
    if (
        complete.is_symlink()
        or not complete.is_file()
        or complete.read_text(encoding="utf-8") != "complete\n"
    ):
      raise RuntimeError("probe completion sentinel is invalid")
  elif complete.exists() or complete.is_symlink():
    raise RuntimeError("probe output completed before closure validation")
  expected_summary = {
      "cegar-eligibility.csv",
      "row-provenance.json",
      "summary.json",
      *(filename for filename, _ in STRICT_PROBE_STRATA),
  }
  actual_summary = {
      path.name
      for path in (root / "summary").iterdir()
      if path.name != ".complete"
  }
  if actual_summary != expected_summary:
    raise RuntimeError("probe summary topology is incomplete")
  summary_args = argparse.Namespace(
      probe_input=str(probe_input),
      sv_benchmarks=args.sv_benchmarks,
      benchmark_definition=str(root / "generated/cegar-eligibility.xml"),
      probe_plan=str(root / "probe-plan.json"),
      output_dir=None,
  )
  with tempfile.TemporaryDirectory(
      prefix=f"vguide-{cohort}-probe-summary-check."
  ) as temp:
    summary_args.output_dir = temp
    write_strict_probe_summary(summary_args, cohort)
    for candidate in Path(temp).iterdir():
      expected = root / "summary" / candidate.name
      if (
          not expected.is_file()
          or expected.is_symlink()
          or candidate.read_bytes() != expected.read_bytes()
      ):
        raise RuntimeError("probe summary does not reproduce exactly")
  artifact = root / "provenance/artifact-manifest.json"
  validate_artifact_manifest(root, artifact, {"summary/.complete"})
  mandatory = (
      "input/research/inventory.sha256",
      "provenance/build.log",
      "provenance/cgroup-check.log",
      "provenance/machine-preflight-start.json",
      "provenance/machine-preflight-end.json",
      "provenance/machine-preflight-check.json",
      "provenance/research-verification-final.log",
      "provenance/runtime-verification-final.log",
      "provenance/runtime-closure.txt",
  )
  for relative in mandatory:
    path = root / relative
    if not path.is_file() or path.is_symlink():
      raise RuntimeError(f"probe closure lacks mandatory evidence: {relative}")
  manifest = baseline.load_task_manifest(manifest_path)
  plan_path = root / "probe-plan.json"
  plan = json.loads(plan_path.read_text(encoding="utf-8"))
  authenticated = load_screen_plan(
      plan_path,
      manifest,
      manifest_path,
      profile["host"],
      args.sv_benchmarks,
      root / "generated/cegar-eligibility.xml",
      plan_schema=profile["plan_schema"],
      repetition=1,
      display=PROBE_DISPLAY,
      time_limit="900 s",
      taint_schema=profile["taint_schema"],
      definition_validator=validate_probe_definition,
      hard_threshold=200,
  )
  markers = sorted((root / "provenance/attempts").glob("*.json"))
  records = {
      marker.stem: validate_formal_attempt_marker(
          marker,
          root,
          manifest_path,
          args.sv_benchmarks,
          profile["host"],
          f"{cohort}-probe",
      )
      for marker in markers
  }
  expected_attempts = {
      "repetition-1": {
          "role": "primary",
          "result_sha256": plan["primary"]["sha256"],
          "definition_sha256": baseline.sha256_file(
              root / "generated/cegar-eligibility.xml"
          ),
          "tasks": sorted(manifest),
      }
  }
  for entry in plan["replacements"]:
    expected_attempts[Path(entry["path"]).parent.name] = {
        "role": "replacement",
        "result_sha256": entry["sha256"],
        "definition_sha256": entry["definition_sha256"],
        "tasks": entry["result_tasks"],
    }
  if set(records) != set(expected_attempts):
    raise RuntimeError("probe attempt markers do not exactly match the plan")
  for label, expected in expected_attempts.items():
    record = records[label]
    actual = {
        "role": record["role"],
        "result_sha256": record["files"]["result"]["sha256"],
        "definition_sha256": record["files"]["definition"]["sha256"],
        "tasks": record["result_tasks"],
    }
    if actual != expected or record["repetition"] != 1:
      raise RuntimeError(f"probe attempt marker does not match plan: {label}")
  return {
      "artifact_aggregate_sha256": json.loads(
          artifact.read_text(encoding="utf-8")
      )["aggregate_sha256"],
      "attempt_count": len(records),
      "result_count": 1 + len(authenticated["replacement_sha256"]),
      "complete": args.require_complete,
      "valid": True,
  }


def validate_cap8_probe_closure(args):
  return validate_strict_probe_closure(args, "cap8")


def validate_cap16_probe_closure(args):
  return validate_strict_probe_closure(args, "cap16")


def command_validate_cap8_probe_closure(args):
  print(json.dumps(validate_cap8_probe_closure(args), sort_keys=True))


def command_validate_cap16_probe_closure(args):
  print(json.dumps(validate_cap16_probe_closure(args), sort_keys=True))


def command_write_complete_sentinel(args):
  output = Path(args.output)
  if output.exists() or output.is_symlink():
    raise RuntimeError("formal completion sentinel already exists")
  output.parent.mkdir(parents=True, exist_ok=True)
  temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
  descriptor = os.open(
      temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
  )
  try:
    os.write(descriptor, b"complete\n")
    os.fsync(descriptor)
  finally:
    os.close(descriptor)
  os.replace(temporary, output)
  directory = os.open(output.parent, os.O_RDONLY)
  try:
    os.fsync(directory)
  finally:
    os.close(directory)


def formal_monitor_lines(path, allow_trailing_nul=False):
  data = Path(path).read_bytes()
  stripped = data.rstrip(b"\0")
  if stripped != data:
    if not allow_trailing_nul:
      raise RuntimeError("formal load monitor has trailing NUL padding")
    if not stripped.endswith(b"\n"):
      raise RuntimeError("formal load monitor NUL padding truncates a sample")
    data = stripped
  if b"\0" in data:
    raise RuntimeError("formal load monitor contains embedded NUL bytes")
  try:
    return data.decode("utf-8").splitlines()
  except UnicodeDecodeError as error:
    raise RuntimeError("formal load monitor is not UTF-8") from error


def load_formal_contention_intervals(path, allow_trailing_nul=False):
  lines = formal_monitor_lines(path, allow_trailing_nul)
  if len(lines) < 2:
    raise RuntimeError("formal load monitor has no samples")
  header = json.loads(lines[0])
  if not isinstance(header, dict) or header != {
      "schema_version": FORMAL_LOAD_MONITOR_SCHEMA,
      "p_core_cpus": list(FORMAL_P_CORE_CPUS),
      "foreign_process_cpu_percent": FORMAL_FOREIGN_CPU_PERCENT,
      "minimum_consecutive_seconds": FORMAL_FOREIGN_CPU_SECONDS,
      "sample_interval_seconds": FORMAL_LOAD_SAMPLE_SECONDS,
      "excluded_process_root": (
          header.get("excluded_process_root")
          if isinstance(header, dict)
          else None
      ),
  } or not isinstance(header.get("excluded_process_root"), int):
    raise RuntimeError("formal load-monitor policy does not match")
  intervals = []
  coverage_start = None
  previous = None
  for line in lines[1:]:
    sample = json.loads(line)
    if (
        not isinstance(sample, dict)
        or set(sample) != {"timestamp", "elapsed_seconds", "offenders"}
        or not isinstance(sample["elapsed_seconds"], (int, float))
        or sample["elapsed_seconds"] <= 0
    ):
      raise RuntimeError("formal load-monitor sample topology is not exact")
    timestamp = datetime.datetime.fromisoformat(sample["timestamp"])
    if timestamp.tzinfo is None or (previous is not None and timestamp <= previous):
      raise RuntimeError("formal load-monitor timestamps are invalid")
    if coverage_start is None:
      coverage_start = timestamp - datetime.timedelta(
          seconds=sample["elapsed_seconds"]
      )
    previous = timestamp
    if not isinstance(sample["offenders"], list):
      raise RuntimeError("formal load-monitor offenders are invalid")
    for offender in sample["offenders"]:
      if (
          set(offender) != {
              "pid",
              "uid",
              "comm",
              "cpu_percent",
              "duration_seconds",
              "since",
              "contended",
          }
          or not isinstance(offender["pid"], int)
          or not isinstance(offender["uid"], int)
          or not isinstance(offender["comm"], str)
          or not isinstance(offender["cpu_percent"], (int, float))
          or not isinstance(offender["duration_seconds"], (int, float))
          or not isinstance(offender["contended"], bool)
      ):
        raise RuntimeError("formal load-monitor offender topology is not exact")
      since = datetime.datetime.fromisoformat(offender["since"])
      expected = offender["duration_seconds"] >= FORMAL_FOREIGN_CPU_SECONDS
      if (
          since.tzinfo is None
          or since > timestamp
          or offender["cpu_percent"] < FORMAL_FOREIGN_CPU_PERCENT
          or offender["contended"] != expected
      ):
        raise RuntimeError("formal load-monitor offender is inconsistent")
      if offender["contended"]:
        intervals.append((since, timestamp))
  return intervals, coverage_start, previous


def match_benchexec_log_task(name, manifest):
  try:
    return baseline.match_result_task(name, manifest)
  except RuntimeError:
    return baseline.match_result_task(f"c/{name}", manifest)


def run_taints(
    result,
    log,
    load_monitor,
    manifest,
    display=FORMAL_DISPLAY,
    time_limit="900 s",
    allow_trailing_nul=False,
    allow_final_log_only_completion=False,
    allow_missing_monitor_coverage=False,
):
  result = Path(result).resolve()
  metadata = (
      probe_result_metadata(result, allow_incomplete=True)
      if display == PROBE_DISPLAY
      else result_metadata(
          result, display, time_limit, allow_incomplete=True
      )
  )
  result_tasks = result_task_names(result, manifest)
  subset = {task: manifest[task] for task in result_tasks}
  rows = {
      row["task"]: row
      for row in baseline.parse_result_rows(result, subset, 200)
  }
  intervals, monitor_start, monitor_end = load_formal_contention_intervals(
      load_monitor, allow_trailing_nul
  )
  start_date = datetime.datetime.fromisoformat(metadata["starttime"])
  result_end = (
      datetime.datetime.fromisoformat(metadata["endtime"])
      if metadata["endtime"]
      else None
  )
  day = start_date.date()
  previous_clock = start_date.timetz().replace(tzinfo=None)
  starts = {}
  ends = {}
  pattern = re.compile(
      r"^(\d{2}:\d{2}:\d{2})\s+(?:(starting)\s+)?(\S+\.yml)(?:\s+.*)?$"
  )
  log_bytes = Path(log).read_bytes()
  if b"\0" in log_bytes:
    raise RuntimeError("BenchExec log contains NUL bytes")
  for line in log_bytes.decode("utf-8").splitlines():
    match = pattern.match(line)
    if not match:
      continue
    clock = datetime.time.fromisoformat(match.group(1))
    if (
        clock < previous_clock
        and (
            datetime.datetime.combine(day, previous_clock)
            - datetime.datetime.combine(day, clock)
        ).total_seconds()
        > 12 * 60 * 60
    ):
      day += datetime.timedelta(days=1)
    previous_clock = clock
    timestamp = datetime.datetime.combine(day, clock, start_date.tzinfo)
    task = match_benchexec_log_task(match.group(3), subset)
    target = starts if match.group(2) else ends
    if task in target:
      raise RuntimeError(f"duplicate BenchExec log event for {task}")
    target[task] = timestamp
  if set(ends) - set(starts):
    raise RuntimeError("BenchExec log completes a task that it never started")
  if any(ended < starts[task] for task, ended in ends.items()):
    raise RuntimeError("BenchExec log completes a task before it starts")
  if (
      (monitor_end is None and not allow_missing_monitor_coverage)
      or (
          monitor_end is not None
          and any(
              timestamp > monitor_end
              for timestamp in (*starts.values(), *ends.values())
          )
      )
  ):
    raise RuntimeError(
        "BenchExec log event occurs after load monitor ended; "
        "completed task was not fully observed"
    )
  complete = {task for task, row in rows.items() if row_is_complete(row)}
  logged_complete = set(ends)
  extra_logged_complete = logged_complete - complete
  recovered_trailing_completion = (
      allow_final_log_only_completion
      and allow_trailing_nul
      and metadata["incomplete"]
      and Path(load_monitor).read_bytes().endswith(b"\0")
      and complete <= logged_complete
      and len(extra_logged_complete) == 1
      and next(reversed(ends)) in extra_logged_complete
  )
  recovered_attempt_5_final_log_only_pending = (
      not allow_final_log_only_completion
      and allow_trailing_nul
      and metadata["incomplete"]
      and Path(load_monitor).read_bytes().endswith(b"\0")
      and complete <= logged_complete
      and extra_logged_complete
      == {FROZEN_CAP16_ATHENA_ATTEMPT_5_FINAL_LOG_ONLY_PENDING_TASK}
      and next(reversed(ends))
      == FROZEN_CAP16_ATHENA_ATTEMPT_5_FINAL_LOG_ONLY_PENDING_TASK
      and frozen_attempt_5_final_log_only_pending(result, log, load_monitor)
  )
  if (
      complete != logged_complete
      and not recovered_trailing_completion
      and not recovered_attempt_5_final_log_only_pending
  ):
    raise RuntimeError("BenchExec log and complete result rows do not match")
  tainted = {
      task: "interrupted_incomplete"
      for task, row in rows.items()
      if not row_is_complete(row)
  }
  for task, started in starts.items():
    ended = ends.get(task, monitor_end)
    if ended is None:
      raise RuntimeError("load monitor ended before an active task could be bounded")
    if (task in ends and ended < started) or (
        task in complete and result_end is not None and ended > result_end
    ):
      raise RuntimeError("BenchExec task timeline is invalid")
    ended += datetime.timedelta(seconds=1)
    if result_end is not None:
      ended = min(ended, result_end)
    if (
        allow_missing_monitor_coverage
        and task in complete
        and (started < monitor_start or ended > monitor_end)
    ):
      tainted.setdefault(task, "missing_load_monitor_coverage")
    if any(started <= stop and ended >= begin for begin, stop in intervals):
      tainted.setdefault(task, "foreign_p_core_contention")
  return tainted


def command_formal_taint(args):
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"formal taint output already exists: {output}")
  manifest = baseline.load_task_manifest(args.manifest)
  primary_hash = baseline.sha256_file(Path(args.result))
  recovery_fields = {
      name: getattr(args, name, None)
      for name in (
          "attempt_marker",
          "output_root",
          "sv_benchmarks",
          "host",
          "mode",
      )
  }
  supplied = [value is not None for value in recovery_fields.values()]
  if any(supplied) and not all(supplied):
    raise RuntimeError(
        "formal taint recovery authentication is incomplete"
    )
  allow_trailing_nul = False
  allow_final_log_only_completion = False
  if all(supplied):
    root = Path(args.output_root).resolve()
    record = validate_formal_attempt_marker(
        args.attempt_marker,
        root,
        Path(args.manifest).resolve(),
        args.sv_benchmarks,
        args.host,
        args.mode,
    )
    if record["repetition"] != args.repetition:
      raise RuntimeError("formal taint attempt repetition does not match")
    for argument, evidence in (
        ("result", "result"),
        ("benchexec_log", "benchexec_log"),
        ("load_monitor", "load_monitor"),
    ):
      expected = (root / record["files"][evidence]["path"]).resolve()
      if Path(getattr(args, argument)).resolve() != expected:
        raise RuntimeError(
            f"formal taint {argument.replace('_', ' ')} does not match marker"
        )
    allow_trailing_nul = record["benchexec_exit"] == 125
    allow_final_log_only_completion = (
        marker_authorizes_final_log_only_completion(record)
    )
  tainted = run_taints(
      args.result,
      args.benchexec_log,
      args.load_monitor,
      manifest,
      allow_trailing_nul=allow_trailing_nul,
      allow_final_log_only_completion=allow_final_log_only_completion,
  )
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps({
      "schema_version": FORMAL_TAINT_SCHEMA,
      "repetition": args.repetition,
      "primary_result_sha256": primary_hash,
      "tasks": [
          {"task": task, "reason": tainted[task]}
          for task in sorted(tainted)
      ],
  }, indent=2) + "\n", encoding="utf-8")
  print(output)


def command_screen_taint(args):
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"screen taint output already exists: {output}")
  manifest = baseline.load_task_manifest(args.manifest)
  primary_hash = baseline.sha256_file(Path(args.result))
  tainted = run_taints(
      args.result,
      args.benchexec_log,
      args.load_monitor,
      manifest,
      DISCOVERY_DISPLAY,
      "120 s",
  )
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps({
      "schema_version": SCREEN_TAINT_SCHEMA,
      "repetition": 1,
      "primary_result_sha256": primary_hash,
      "tasks": [
          {"task": task, "reason": tainted[task]}
          for task in sorted(tainted)
      ],
  }, indent=2) + "\n", encoding="utf-8")
  print(output)


def write_probe_taint(args, cohort):
  profile = strict_probe_profile(cohort)
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"probe taint output already exists: {output}")
  manifest = baseline.load_task_manifest(args.manifest)
  primary_hash = baseline.sha256_file(Path(args.result))
  tainted = run_taints(
      args.result,
      args.benchexec_log,
      args.load_monitor,
      manifest,
      PROBE_DISPLAY,
      "900 s",
  )
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps({
      "schema_version": profile["taint_schema"],
      "repetition": 1,
      "primary_result_sha256": primary_hash,
      "tasks": [
          {"task": task, "reason": tainted[task]}
          for task in sorted(tainted)
      ],
  }, indent=2) + "\n", encoding="utf-8")
  print(output)


def command_cap8_probe_taint(args):
  write_probe_taint(args, "cap8")


def command_probe_taint(args):
  write_probe_taint(args, "cap16")


def row_is_complete(row):
  return (
      bool(row["status"])
      and bool(row["category"])
      and row["cpu_time_seconds"] is not None
      and row["wall_time_seconds"] is not None
  )


def task_set_sha256(tasks):
  return sha256_text("".join(f"{task}\n" for task in sorted(tasks)))


def recovery_file_entry(path, root):
  declared = Path(path)
  path = Path(os.path.abspath(declared))
  root = Path(root).resolve()
  try:
    relative = path.relative_to(root)
  except ValueError as error:
    raise RuntimeError("formal recovery evidence escapes output root") from error
  if (
      declared.resolve() != path
      or path.is_symlink()
      or not path.is_file()
  ):
    raise RuntimeError("formal recovery evidence is not a regular file")
  return {
      "path": relative.as_posix(),
      "sha256": baseline.sha256_file(path),
  }


def validate_recovery_file_entry(root, entry, label):
  if (
      not isinstance(entry, dict)
      or set(entry) != {"path", "sha256"}
      or not isinstance(entry["path"], str)
      or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
  ):
    raise RuntimeError(f"{label} file entry is invalid")
  relative = Path(entry["path"])
  if relative.is_absolute() or ".." in relative.parts:
    raise RuntimeError(f"{label} file entry escapes output root")
  path = Path(root).resolve() / relative
  if (
      path.resolve() != Path(os.path.abspath(path))
      or path.is_symlink()
      or not path.is_file()
      or baseline.sha256_file(path) != entry["sha256"]
  ):
    raise RuntimeError(f"{label} file entry differs")
  return path


def load_formal_recovery_seed(path, manifest_path, manifest):
  path = Path(path).resolve()
  data = json.loads(path.read_text(encoding="utf-8"))
  provenance_keys = {
      "definition",
      "result",
      "benchexec_log",
      "load_monitor",
      "taint_manifest",
      "boot_evidence",
      "runtime_closure",
      "migration_manifest",
      "attempt_marker",
      "machine_before",
      "process_descriptor",
  }
  if (
      not isinstance(data, dict)
      or set(data) != {
          "schema_version",
          "parent_manifest_sha256",
          "rows",
      }
      or data["schema_version"] != FORMAL_RECOVERY_SEED_SCHEMA
      or data["parent_manifest_sha256"]
      != baseline.sha256_file(Path(manifest_path))
      or not isinstance(data["rows"], list)
  ):
    raise RuntimeError("formal recovery seed ledger is invalid")
  identities = []
  rows = {}
  for entry in data["rows"]:
    if (
        not isinstance(entry, dict)
        or set(entry) != {
            "repetition",
            "task",
            "classification",
            "row",
            "provenance",
        }
        or entry["repetition"] not in {1, 2}
        or not isinstance(entry["task"], str)
        or entry["task"] not in manifest
        or entry["classification"]
        not in {"accepted_and_reusable", "verifier_failure"}
        or not isinstance(entry["row"], dict)
        or entry["row"].get("task") != entry["task"]
        or not row_is_complete(entry["row"])
        or not isinstance(entry["provenance"], dict)
        or set(entry["provenance"]) != provenance_keys | {"attempt_id"}
        or not isinstance(entry["provenance"]["attempt_id"], str)
        or not entry["provenance"]["attempt_id"]
        or any(
            value is not None
            and (
                not isinstance(value, dict)
                or set(value) != {"path", "sha256"}
                or not isinstance(value["path"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
            )
            for label, value in entry["provenance"].items()
            if label != "attempt_id"
        )
        or entry["provenance"]["definition"] is None
        or entry["provenance"]["result"] is None
        or entry["provenance"]["benchexec_log"] is None
        or entry["provenance"]["load_monitor"] is None
        or entry["provenance"]["taint_manifest"] is None
        or entry["provenance"]["boot_evidence"] is None
        or entry["provenance"]["runtime_closure"] is None
        or entry["provenance"]["migration_manifest"] is None
    ):
      raise RuntimeError("formal recovery seed row is invalid")
    expected_classification = (
        "accepted_and_reusable"
        if entry["row"]["category"] == "correct"
        or is_analysis_unsolved(entry["row"])
        else "verifier_failure"
    )
    if entry["classification"] != expected_classification:
      raise RuntimeError("formal recovery seed classification differs")
    identity = (entry["repetition"], entry["task"])
    if identity in rows:
      raise RuntimeError("formal recovery seed row is duplicated")
    identities.append(identity)
    rows[identity] = entry
  if identities != sorted(identities):
    raise RuntimeError("formal recovery seed rows are not sorted")
  return data, rows


def validate_formal_boot_evidence(path, attempt_id, host):
  data = json.loads(Path(path).read_text(encoding="utf-8"))
  if (
      not isinstance(data, dict)
      or set(data) != {
          "schema_version",
          "attempt_id",
          "host",
          "boot_id",
          "method",
          "records",
      }
      or data["schema_version"] != FORMAL_RECOVERY_BOOT_EVIDENCE_SCHEMA
      or data["attempt_id"] != attempt_id
      or data["host"] != host
      or not re.fullmatch(
          r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
          r"[0-9a-f]{4}-[0-9a-f]{12}",
          data["boot_id"],
      )
      or data["method"]
      not in {"systemd_journal_record", "owned_process_identity"}
      or not isinstance(data["records"], list)
      or not data["records"]
  ):
    raise RuntimeError("formal recovery boot evidence is invalid")
  encoded = json.dumps(data["records"], sort_keys=True)
  if data["boot_id"].replace("-", "") not in encoded.replace("-", "") or (
      attempt_id not in encoded
  ):
    raise RuntimeError("formal recovery boot evidence does not bind the attempt")
  if data["method"] == "systemd_journal_record":
    if not any(
        isinstance(record, dict)
        and record.get("_BOOT_ID", "").replace("-", "")
        == data["boot_id"].replace("-", "")
        and record.get("_HOSTNAME") == host
        and attempt_id in record.get("MESSAGE", "")
        for record in data["records"]
    ):
      raise RuntimeError("formal recovery journal boot record differs")
  elif not any(
      isinstance(record, dict)
      and record.get("boot_id") == data["boot_id"]
      and attempt_id in json.dumps(record.get("argv"), sort_keys=True)
      for record in data["records"]
  ):
    raise RuntimeError("formal recovery process boot record differs")
  return data


def command_build_formal_recovery_seed(args):
  root = Path(args.output_root).resolve()
  manifest_path = Path(args.manifest).resolve()
  manifest = baseline.load_task_manifest(manifest_path)
  migration_path = Path(args.migration_manifest).resolve()
  migration = json.loads(migration_path.read_text(encoding="utf-8"))
  expected_host = "athena" if args.mode == "cap16" else "valkyrie"
  if (
      not isinstance(migration, dict)
      or set(migration) != {
          "schema_version",
          "parent_manifest_sha256",
          "mode",
          "host",
          "attempts",
      }
      or migration["schema_version"] != FORMAL_RECOVERY_MIGRATION_SCHEMA
      or migration["parent_manifest_sha256"]
      != baseline.sha256_file(manifest_path)
      or migration["mode"] != args.mode
      or migration["host"] != expected_host
      or not isinstance(migration["attempts"], list)
  ):
    raise RuntimeError("formal recovery migration manifest is invalid")
  migration_entry = recovery_file_entry(migration_path, root)
  rows = {}
  attempt_ids = set()
  file_keys = {
      "definition",
      "result",
      "benchexec_log",
      "load_monitor",
      "taint_manifest",
      "boot_evidence",
      "runtime_closure",
      "attempt_marker",
      "process_descriptor",
      "machine_before",
  }
  for attempt in migration["attempts"]:
    if (
        not isinstance(attempt, dict)
        or set(attempt) != {
            "id",
            "repetition",
            "completion_state",
            "task_set_sha256",
            "runtime",
            "files",
        }
        or not isinstance(attempt["id"], str)
        or not attempt["id"]
        or attempt["id"] in attempt_ids
        or attempt["repetition"] not in {1, 2}
        or attempt["completion_state"] not in {"complete", "interrupted"}
        or not re.fullmatch(r"[0-9a-f]{64}", attempt["task_set_sha256"])
        or not isinstance(attempt["files"], dict)
        or set(attempt["files"]) != file_keys
    ):
      raise RuntimeError("formal recovery migration attempt is invalid")
    validate_formal_migration_runtime(attempt["runtime"], args.mode)
    attempt_ids.add(attempt["id"])
    files = {}
    for label, entry in attempt["files"].items():
      if entry is None:
        if label not in {
            "attempt_marker",
            "process_descriptor",
            "machine_before",
        }:
          raise RuntimeError("formal recovery migration evidence is missing")
        files[label] = None
      else:
        files[label] = validate_recovery_file_entry(
            root, entry, f"migration {label}"
        )
    boot = validate_formal_boot_evidence(
        files["boot_evidence"], attempt["id"], expected_host
    )
    if (
        baseline.sha256_file(files["runtime_closure"])
        != attempt["runtime"]["configuration_closure_sha256"]
    ):
      raise RuntimeError("formal recovery migration runtime closure differs")
    definition_tasks = migration_definition_manifest_tasks(
        files["definition"],
        manifest_path,
        manifest,
        args.sv_benchmarks,
    )
    if attempt["task_set_sha256"] != task_set_sha256(definition_tasks):
      raise RuntimeError("formal recovery migration task set differs")
    metadata = result_metadata(
        files["result"], FORMAL_DISPLAY, "900 s", allow_incomplete=True
    )
    if (
        metadata["host"] != expected_host
        or metadata["incomplete"]
        != (attempt["completion_state"] == "interrupted")
    ):
      raise RuntimeError("formal recovery migration completion state differs")
    result_tasks = result_task_names(files["result"], manifest)
    if not set(result_tasks) <= set(definition_tasks):
      raise RuntimeError("formal recovery migration result exceeds its task set")
    subset = {task: manifest[task] for task in result_tasks}
    validate_result_run_topology(
        files["result"], subset, args.sv_benchmarks, files["definition"]
    )
    parsed = {
        row["task"]: row
        for row in baseline.parse_result_rows(files["result"], subset, 200)
    }
    tainted = validate_taint_manifest(
        json.loads(files["taint_manifest"].read_text(encoding="utf-8")),
        attempt["repetition"],
        baseline.sha256_file(files["result"]),
        manifest,
    )
    marker = None
    descriptor = None
    if files["process_descriptor"] is not None:
      descriptor = load_formal_process_descriptor(
          files["process_descriptor"],
          root,
          args.mode,
          attempt["id"],
          expected_host,
      )
      launcher_argv = descriptor["identities"]["benchexec-launcher"]["argv"]
      workers = int(launcher_argv[launcher_argv.index("-N") + 1])
      if workers != attempt["runtime"]["workers"]:
        raise RuntimeError("formal recovery migration workers differ")
    if files["attempt_marker"] is not None:
      marker = validate_formal_attempt_marker(
          files["attempt_marker"],
          root,
          manifest_path,
          args.sv_benchmarks,
          expected_host,
          args.mode,
      )
      expected_marker_files = {
          "definition": files["definition"],
          "result": files["result"],
          "benchexec_log": files["benchexec_log"],
          "load_monitor": files["load_monitor"],
          "process_descriptor": files["process_descriptor"],
          "machine_before": files["machine_before"],
      }
      if (
          marker["label"] != attempt["id"]
          or marker["repetition"] != attempt["repetition"]
          or sorted(marker["result_tasks"]) != sorted(result_tasks)
          or any(
              path is None
              or marker["files"][label]
              != attempt["files"][label]
              for label, path in expected_marker_files.items()
          )
      ):
        raise RuntimeError("formal recovery migration marker differs")
      if boot["method"] == "owned_process_identity":
        expected_processes = [
            json.loads(
                (root / marker["files"][label]["path"]).read_text(
                    encoding="utf-8"
                )
            )
            for label in ("benchexec_process", "monitor_process")
        ]
        if (
            boot["records"] != expected_processes
            or any(
                record.get("boot_id") != boot["boot_id"]
                for record in expected_processes
            )
        ):
          raise RuntimeError(
              "formal recovery migration process boot record differs"
          )
    recomputed_taint = run_taints(
        files["result"],
        files["benchexec_log"],
        files["load_monitor"],
        manifest,
        allow_trailing_nul=(
            marker is not None and marker["benchexec_exit"] == 125
        ),
        allow_final_log_only_completion=(
            marker is not None
            and marker_authorizes_final_log_only_completion(marker)
        ),
        allow_missing_monitor_coverage=marker is None,
    )
    if tainted != recomputed_taint:
      raise RuntimeError("formal recovery migration taint differs")
    if not set(tainted) <= set(definition_tasks):
      raise RuntimeError("formal recovery migration taint exceeds its task set")
    for task in sorted(result_tasks):
      row = parsed[task]
      if not row_is_complete(row) or task in tainted:
        continue
      classification = (
          "accepted_and_reusable"
          if row["category"] == "correct" or is_analysis_unsolved(row)
          else "verifier_failure"
      )
      identity = (attempt["repetition"], task)
      if identity in rows:
        raise RuntimeError("formal recovery migration has conflicting rows")
      rows[identity] = {
          "repetition": attempt["repetition"],
          "task": task,
          "classification": classification,
          "row": row,
          "provenance": {
              "attempt_id": attempt["id"],
              **{
                  label: (
                      None
                      if entry is None
                      else attempt["files"][label]
                  )
                  for label, entry in files.items()
              },
              "migration_manifest": migration_entry,
          },
      }
  seed = {
      "schema_version": FORMAL_RECOVERY_SEED_SCHEMA,
      "parent_manifest_sha256": baseline.sha256_file(manifest_path),
      "rows": [rows[identity] for identity in sorted(rows)],
  }
  if args.output is None:
    return seed
  output = Path(args.output).resolve()
  if output.exists() or output.is_symlink():
    raise RuntimeError("formal recovery seed output already exists")
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(
      json.dumps(seed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
  )
  load_formal_recovery_seed(output, manifest_path, manifest)
  validate_seed_evidence(
      root,
      rows,
      manifest,
      expected_host,
      manifest_path,
      args.sv_benchmarks,
      args.mode,
  )
  print(output)


def validate_formal_runtime(runtime, allowed_workers):
  if (
      not isinstance(runtime, dict)
      or set(runtime) != {
          "cpachecker_commit",
          "sv_benchmarks_commit",
          "benchexec_commit",
          "jdk_sha256",
          "configuration_closure_sha256",
          "solver",
          "limits",
          "workers",
          "cores_per_worker",
          "p_cores",
      }
      or not re.fullmatch(r"[0-9a-f]{40}", runtime["cpachecker_commit"])
      or not re.fullmatch(
          r"[0-9a-f]{40}", runtime["sv_benchmarks_commit"]
      )
      or not re.fullmatch(r"[0-9a-f]{40}", runtime["benchexec_commit"])
      or not re.fullmatch(r"[0-9a-f]{64}", runtime["jdk_sha256"])
      or not re.fullmatch(
          r"[0-9a-f]{64}", runtime["configuration_closure_sha256"]
      )
      or not isinstance(runtime["solver"], str)
      or runtime["solver"] != "MathSAT5"
      or any(
          runtime[name] != value
          for name, value in FORMAL_RUNTIME_COMMITS.items()
      )
      or runtime["limits"]
      != {
          "cpu": "900 s",
          "hard_cpu": "910 s",
          "wall": "920 s",
          "memory": "15 GB",
          "heap": "10000M",
      }
      or runtime["workers"] not in allowed_workers
      or runtime["cores_per_worker"] != 4
      or runtime["p_cores"] != FORMAL_P_CORE_LIST
  ):
    raise RuntimeError("formal recovery runtime closure is invalid")


def validate_formal_recovery_runtime(runtime, mode):
  validate_formal_runtime(runtime, {1 if mode == "cap16" else 2})


def validate_formal_migration_runtime(runtime, mode):
  validate_formal_runtime(runtime, {1, 2} if mode == "cap16" else {2})


def load_formal_recovery_protocol(
    path, seed_path, manifest_path, property_file
):
  path = Path(path).resolve()
  seed_path = Path(seed_path).resolve()
  manifest_path = Path(manifest_path).resolve()
  property_file = Path(property_file).resolve()
  manifest = baseline.load_task_manifest(manifest_path)
  seed, seed_rows = load_formal_recovery_seed(
      seed_path, manifest_path, manifest
  )
  data = json.loads(path.read_text(encoding="utf-8"))
  if (
      not isinstance(data, dict)
      or set(data) != {
          "schema_version",
          "source_commit",
          "mode",
          "host",
          "parent_manifest_sha256",
          "property_sha256",
          "seed_ledger_sha256",
          "runtime",
          "shard_size",
          "repetitions",
      }
      or data["schema_version"] != FORMAL_RECOVERY_PROTOCOL_SCHEMA
      or not re.fullmatch(r"[0-9a-f]{40}", data["source_commit"])
      or data["mode"] not in {"cap8", "cap16"}
      or data["host"]
      != ("athena" if data["mode"] == "cap16" else "valkyrie")
      or data["parent_manifest_sha256"]
      != baseline.sha256_file(manifest_path)
      or data["property_sha256"] != baseline.sha256_file(property_file)
      or data["seed_ledger_sha256"] != baseline.sha256_file(seed_path)
      or data["shard_size"] != (8 if data["mode"] == "cap16" else 16)
      or not isinstance(data["repetitions"], list)
      or len(data["repetitions"]) != 2
  ):
    raise RuntimeError("formal recovery protocol identity is invalid")
  validate_formal_recovery_runtime(data["runtime"], data["mode"])
  parent_order = list(manifest)
  for repetition, record in enumerate(data["repetitions"], start=1):
    settled = {
        task
        for (candidate_repetition, task), _ in seed_rows.items()
        if candidate_repetition == repetition
    }
    expected_pending = [
        task for task in parent_order if task not in settled
    ]
    if (
        not isinstance(record, dict)
        or set(record) != {
            "repetition",
            "pending_tasks",
            "pending_task_set_sha256",
            "shards",
        }
        or record["repetition"] != repetition
        or record["pending_tasks"] != expected_pending
        or record["pending_task_set_sha256"]
        != task_set_sha256(expected_pending)
        or not isinstance(record["shards"], list)
    ):
      raise RuntimeError("formal recovery repetition protocol differs")
    expected_shards = []
    for index in range(0, len(expected_pending), data["shard_size"]):
      tasks = expected_pending[index:index + data["shard_size"]]
      digest = task_set_sha256(tasks)
      expected_shards.append({
          "index": len(expected_shards),
          "id": f"r{repetition}-s{len(expected_shards):03d}-{digest[:12]}",
          "task_set_sha256": digest,
          "tasks": tasks,
      })
    if record["shards"] != expected_shards:
      raise RuntimeError("formal recovery shard partition differs")
  return data, seed, manifest, seed_rows


def command_freeze_formal_recovery_protocol(args):
  output = Path(args.output).resolve()
  if output.exists() or output.is_symlink():
    raise RuntimeError("formal recovery protocol output already exists")
  manifest_path = Path(args.manifest).resolve()
  property_file = Path(args.property_file).resolve()
  manifest = baseline.load_task_manifest(manifest_path)
  _, seed_rows = load_formal_recovery_seed(
      args.seed_ledger, manifest_path, manifest
  )
  runtime = json.loads(Path(args.runtime_closure).read_text(encoding="utf-8"))
  validate_formal_recovery_runtime(runtime, args.mode)
  repetitions = []
  parent_order = list(manifest)
  shard_size = 8 if args.mode == "cap16" else 16
  for repetition in (1, 2):
    settled = {
        task
        for (candidate_repetition, task), _ in seed_rows.items()
        if candidate_repetition == repetition
    }
    pending = [task for task in parent_order if task not in settled]
    shards = []
    for start in range(0, len(pending), shard_size):
      tasks = pending[start:start + shard_size]
      digest = task_set_sha256(tasks)
      shards.append({
          "index": len(shards),
          "id": f"r{repetition}-s{len(shards):03d}-{digest[:12]}",
          "task_set_sha256": digest,
          "tasks": tasks,
      })
    repetitions.append({
        "repetition": repetition,
        "pending_tasks": pending,
        "pending_task_set_sha256": task_set_sha256(pending),
        "shards": shards,
    })
  protocol = {
      "schema_version": FORMAL_RECOVERY_PROTOCOL_SCHEMA,
      "source_commit": args.source_commit,
      "mode": args.mode,
      "host": "athena" if args.mode == "cap16" else "valkyrie",
      "parent_manifest_sha256": baseline.sha256_file(manifest_path),
      "property_sha256": baseline.sha256_file(property_file),
      "seed_ledger_sha256": baseline.sha256_file(Path(args.seed_ledger)),
      "runtime": runtime,
      "shard_size": shard_size,
      "repetitions": repetitions,
  }
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(
      json.dumps(protocol, indent=2, sort_keys=True) + "\n",
      encoding="utf-8",
  )
  load_formal_recovery_protocol(
      output, args.seed_ledger, manifest_path, property_file
  )
  print(output)


def validate_seed_evidence(
    root,
    seed_rows,
    manifest,
    host,
    manifest_path,
    sv_benchmarks,
    mode,
):
  root = Path(root).resolve()
  migrations = {}
  for entry in seed_rows.values():
    migration_entry = entry["provenance"]["migration_manifest"]
    migration_path = validate_recovery_file_entry(
        root, migration_entry, "seed migration manifest"
    )
    migrations[(migration_entry["path"], migration_entry["sha256"])] = (
        migration_path
    )
  expected_rows = {}
  for migration_path in migrations.values():
    rebuilt = command_build_formal_recovery_seed(argparse.Namespace(
        output_root=str(root),
        migration_manifest=str(migration_path),
        manifest=str(Path(manifest_path).resolve()),
        sv_benchmarks=str(Path(sv_benchmarks).resolve()),
        mode=mode,
        output=None,
    ))
    for row in rebuilt["rows"]:
      identity = (row["repetition"], row["task"])
      if identity in expected_rows:
        raise RuntimeError("formal recovery seed has conflicting migrations")
      expected_rows[identity] = row
  if host != ("athena" if mode == "cap16" else "valkyrie"):
    raise RuntimeError("formal recovery seed host differs")
  if expected_rows != seed_rows:
    raise RuntimeError("formal recovery seed replay differs")


def formal_recovery_ledger_rows(
    root, authorization, marker, taint_entry, manifest
):
  root = Path(root).resolve()
  if (
      not isinstance(marker, dict)
      or marker.get("schema_version") != FORMAL_ATTEMPT_SCHEMA
      or marker.get("label") != authorization["label"]
      or marker.get("role") != "replacement"
      or marker.get("repetition") != authorization["repetition"]
      or not isinstance(marker.get("result_tasks"), list)
      or not set(marker["result_tasks"])
      <= set(authorization["authorized_tasks"])
      or not isinstance(marker.get("files"), dict)
  ):
    raise RuntimeError("formal recovery ledger marker identity is invalid")
  for label, file_entry in marker["files"].items():
    validate_recovery_file_entry(root, file_entry, f"marker {label}")
  result = root / marker["files"]["result"]["path"]
  result_subset = {
      task: manifest[task] for task in marker["result_tasks"]
  }
  parsed = {
      row["task"]: row
      for row in baseline.parse_result_rows(result, result_subset, 200)
  }
  taint_path = validate_recovery_file_entry(
      root, taint_entry, "ledger taint manifest"
  )
  tainted = validate_taint_manifest(
      json.loads(taint_path.read_text(encoding="utf-8")),
      authorization["repetition"],
      marker["files"]["result"]["sha256"],
      manifest,
  )
  recomputed_taint = run_taints(
      result,
      root / marker["files"]["benchexec_log"]["path"],
      root / marker["files"]["load_monitor"]["path"],
      manifest,
      allow_trailing_nul=marker["benchexec_exit"] == 125,
      allow_final_log_only_completion=(
          marker_authorizes_final_log_only_completion(marker)
      ),
  )
  if tainted != recomputed_taint:
    raise RuntimeError("formal recovery ledger taint differs")
  if not set(tainted) <= set(authorization["authorized_tasks"]):
    raise RuntimeError("formal recovery ledger taint exceeds authorization")
  provenance = {
      "definition": marker["files"]["definition"],
      "result": marker["files"]["result"],
      "benchexec_log": marker["files"]["benchexec_log"],
      "load_monitor": marker["files"]["load_monitor"],
      "taint_manifest": taint_entry,
      "attempt_marker": None,
      "machine_before": marker["files"]["machine_before"],
      "process_descriptor": marker["files"]["process_descriptor"],
  }
  rows = []
  for task in authorization["authorized_tasks"]:
    row = parsed.get(task)
    classification, settled = classify_formal_recovery_row(
        row, task in tainted
    )
    if row is not None and not row_is_complete(row) and task not in tainted:
      raise RuntimeError("incomplete formal recovery row is not tainted")
    rows.append({
        "task": task,
        "classification": classification,
        "settled": settled,
        "row": row,
        "provenance": provenance,
    })
  return rows


def load_formal_recovery_ledger(
    root,
    protocol_path,
    seed_path,
    manifest_path,
    property_file,
    sv_benchmarks,
):
  root = Path(root).resolve()
  protocol, seed, manifest, seed_rows = load_formal_recovery_protocol(
      protocol_path, seed_path, manifest_path, property_file
  )
  validate_seed_evidence(
      root,
      seed_rows,
      manifest,
      protocol["host"],
      manifest_path,
      sv_benchmarks,
      protocol["mode"],
  )
  protocol_sha256 = baseline.sha256_file(Path(protocol_path))
  seed_sha256 = baseline.sha256_file(Path(seed_path))
  validation_state = {
      "protocol": protocol,
      "protocol_sha256": protocol_sha256,
      "seed_sha256": seed_sha256,
      "manifest": manifest,
      "manifest_path": Path(manifest_path).resolve(),
      "sv_benchmarks": Path(sv_benchmarks).resolve(),
  }
  settled = dict(seed_rows)
  attempts = []
  entries = root / "provenance/formal-ledger/entries"
  if entries.exists():
    if entries.is_symlink() or not entries.is_dir():
      raise RuntimeError("formal recovery ledger entry root is invalid")
    for path in sorted(entries.iterdir()):
      if path.is_symlink() or not path.is_file() or path.suffix != ".json":
        raise RuntimeError("formal recovery ledger topology is invalid")
      entry = json.loads(path.read_text(encoding="utf-8"))
      if (
          not isinstance(entry, dict)
          or set(entry) != {
              "schema_version",
              "protocol_sha256",
              "seed_ledger_sha256",
              "authorization",
              "attempt_marker",
              "taint_manifest",
              "repetition",
              "shard_id",
              "rows",
          }
          or entry["schema_version"] != FORMAL_RECOVERY_LEDGER_SCHEMA
          or entry["protocol_sha256"] != protocol_sha256
          or entry["seed_ledger_sha256"] != seed_sha256
          or entry["repetition"] not in {1, 2}
          or not isinstance(entry["shard_id"], str)
          or not isinstance(entry["rows"], list)
          or path.stem != entry["attempt_marker"]["sha256"]
      ):
        raise RuntimeError("formal recovery ledger entry is invalid")
      authorization_path = validate_recovery_file_entry(
          root, entry["authorization"], "ledger authorization"
      )
      marker_path = validate_recovery_file_entry(
          root, entry["attempt_marker"], "ledger attempt marker"
      )
      authorization = formal_recovery_authorization(
          root, authorization_path, validation_state
      )
      marker = validate_formal_attempt_marker(
          marker_path,
          root,
          Path(manifest_path).resolve(),
          sv_benchmarks,
          protocol["host"],
          protocol["mode"],
      )
      for identity_name in ("benchexec_process", "monitor_process"):
        identity_path = validate_recovery_file_entry(
            root,
            marker["files"][identity_name],
            f"ledger {identity_name}",
        )
        identity = load_attempt_process_identity(
            identity_path, root, authorization["label"]
        )
        if identity["boot_id"] != authorization["boot_id"]:
          raise RuntimeError(
              "formal recovery ledger process boot differs from authorization"
          )
      expected_rows = formal_recovery_ledger_rows(
          root,
          authorization,
          marker,
          entry["taint_manifest"],
          manifest,
      )
      expected_provenance = {
          **expected_rows[0]["provenance"],
          "attempt_marker": entry["attempt_marker"],
      } if expected_rows else None
      for row in expected_rows:
        row["provenance"] = expected_provenance
      if (
          entry["repetition"] != authorization["repetition"]
          or entry["shard_id"] != authorization["shard_id"]
          or entry["rows"] != expected_rows
      ):
        raise RuntimeError("formal recovery ledger content differs")
      identities = []
      for row in entry["rows"]:
        if (
            not isinstance(row, dict)
            or set(row) != {
                "task",
                "classification",
                "settled",
                "row",
                "provenance",
            }
            or row["task"] not in manifest
            or row["classification"]
            not in {
                "accepted_and_reusable",
                "complete_but_tainted",
                "structurally_incomplete",
                "verifier_failure",
            }
            or row["settled"]
            != (
                row["classification"]
                in {"accepted_and_reusable", "verifier_failure"}
            )
            or (
                row["row"] is not None
                and (
                    not isinstance(row["row"], dict)
                    or row["row"].get("task") != row["task"]
                )
            )
            or not isinstance(row["provenance"], dict)
        ):
          raise RuntimeError("formal recovery ledger row is invalid")
        identities.append(row["task"])
        if row["settled"]:
          identity = (entry["repetition"], row["task"])
          if identity in settled:
            raise RuntimeError("formal recovery ledger has conflicting rows")
          settled[identity] = {
              "repetition": entry["repetition"],
              "task": row["task"],
              "classification": row["classification"],
              "row": row["row"],
              "provenance": row["provenance"],
          }
      if identities != sorted(identities) or len(set(identities)) != len(
          identities
      ):
        raise RuntimeError("formal recovery ledger rows are not sorted")
      attempts.append((path, entry))
  pending = {}
  for record in protocol["repetitions"]:
    repetition = record["repetition"]
    pending[repetition] = [
        task
        for task in record["pending_tasks"]
        if (repetition, task) not in settled
    ]
  abandonments = []
  abandonment_root = root / "provenance/formal-ledger/abandonments"
  if abandonment_root.exists():
    if abandonment_root.is_symlink() or not abandonment_root.is_dir():
      raise RuntimeError("formal recovery abandonment root is invalid")
    for path in sorted(abandonment_root.iterdir()):
      if path.is_symlink() or not path.is_file() or path.suffix != ".json":
        raise RuntimeError("formal recovery abandonment topology is invalid")
      abandonments.append(
          formal_recovery_abandonment(
              root,
              path,
              validation_state,
          )
      )
  rejections = []
  rejection_root = root / "provenance/formal-ledger/rejections"
  if rejection_root.exists():
    if rejection_root.is_symlink() or not rejection_root.is_dir():
      raise RuntimeError("formal recovery rejection root is invalid")
    for path in sorted(rejection_root.iterdir()):
      if path.is_symlink() or not path.is_file() or path.suffix != ".json":
        raise RuntimeError("formal recovery rejection topology is invalid")
      record = json.loads(path.read_text(encoding="utf-8"))
      if (
          not isinstance(record, dict)
          or set(record) != {
              "schema_version",
              "protocol_sha256",
              "seed_ledger_sha256",
              "completion_state",
              "label",
              "authorization",
              "error",
              "error_sha256",
              "rows",
          }
          or record["schema_version"] != FORMAL_RECOVERY_REJECTION_SCHEMA
          or record["protocol_sha256"] != protocol_sha256
          or record["seed_ledger_sha256"] != seed_sha256
          or record["completion_state"] != "invalid_evidence"
          or path.stem != record["label"]
          or not isinstance(record["error"], str)
          or not record["error"]
          or record["error_sha256"] != sha256_text(record["error"])
          or not isinstance(record["rows"], list)
      ):
        raise RuntimeError("formal recovery rejection is invalid")
      authorization_path = validate_recovery_file_entry(
          root, record["authorization"], "rejection authorization"
      )
      authorization = formal_recovery_authorization(
          root, authorization_path, validation_state
      )
      expected_rows = [
          {
              "task": task,
              "classification": "invalid_evidence",
              "settled": False,
          }
          for task in authorization["authorized_tasks"]
      ]
      if (
          authorization["label"] != record["label"]
          or record["rows"] != expected_rows
      ):
        raise RuntimeError("formal recovery rejection rows differ")
      rejections.append(record)
  accepted_labels = {
      entry["attempt_marker"]["path"].rsplit("/", 1)[-1].removesuffix(
          ".json"
      )
      for _, entry in attempts
  }
  abandoned_labels = {record["label"] for record in abandonments}
  rejected_labels = {record["label"] for record in rejections}
  if (
      accepted_labels & abandoned_labels
      or accepted_labels & rejected_labels
      or abandoned_labels & rejected_labels
  ):
    raise RuntimeError("formal recovery attempt has conflicting terminal states")
  return {
      "protocol": protocol,
      "protocol_sha256": protocol_sha256,
      "seed": seed,
      "seed_sha256": seed_sha256,
      "manifest": manifest,
      "manifest_path": Path(manifest_path).resolve(),
      "sv_benchmarks": Path(sv_benchmarks).resolve(),
      "settled": settled,
      "attempts": attempts,
      "abandonments": abandonments,
      "rejections": rejections,
      "pending": pending,
  }


def formal_definition_closure(definition):
  definition = Path(definition).resolve()
  root = ET.parse(definition).getroot()
  files = [definition]
  for node in root.findall(".//includesfile"):
    if not node.text:
      raise RuntimeError("formal recovery definition includes an empty task set")
    task_set = Path(node.text)
    if not task_set.is_absolute():
      task_set = definition.parent / task_set
    files.append(task_set.resolve())
  if len(files) == 1:
    raise RuntimeError("formal recovery definition has no task set")
  return files


def definition_manifest_tasks(
    definition, manifest_path, manifest, sv_benchmarks
):
  tasks = []
  for task_set in formal_definition_closure(definition)[1:]:
    if task_set.is_symlink() or not task_set.is_file():
      raise RuntimeError("formal recovery task set is not a regular file")
    for name in task_set.read_text(encoding="utf-8").splitlines():
      task = baseline.match_result_task(name, manifest)
      if task in tasks:
        raise RuntimeError("formal recovery definition repeats a task")
      tasks.append(task)
  subset = {
      "task_count": len(tasks),
      "tasks": [manifest[task] for task in tasks],
  }
  validate_formal_definition(
      definition,
      manifest_path,
      subset,
      sv_benchmarks,
  )
  return tasks


def migration_definition_manifest_tasks(
    definition, manifest_path, manifest, sv_benchmarks
):
  definition = Path(definition).resolve()
  root = ET.parse(definition).getroot()
  task_sets = []
  for group in root.findall("./rundefinition/tasks"):
    includes = group.findall("includesfile")
    expected_name = f"hard-case-candidates-{group.get('name')}.set"
    if (
        len(includes) != 1
        or not includes[0].text
        or Path(includes[0].text).name != expected_name
    ):
      raise RuntimeError("formal recovery migration task set path is invalid")
    task_sets.append(definition.parent / expected_name)
  tasks = []
  for task_set in task_sets:
    if task_set.is_symlink() or not task_set.is_file():
      raise RuntimeError("formal recovery task set is not a regular file")
    for name in task_set.read_text(encoding="utf-8").splitlines():
      task = baseline.match_result_task(name, manifest)
      if task in tasks:
        raise RuntimeError("formal recovery definition repeats a task")
      tasks.append(task)
  subset = {
      "task_count": len(tasks),
      "tasks": [manifest[task] for task in tasks],
  }
  normalized = ET.fromstring(ET.tostring(root))
  for group in normalized.findall("./rundefinition/tasks"):
    name = group.get("name")
    include = group.find("includesfile")
    property_file = group.find("propertyfile")
    suffix = (
        "c/properties/unreach-call.prp"
        if name == "official"
        else "corpus/properties/unreach-call.prp"
    )
    if (
        name not in {"official", "external"}
        or include is None
        or property_file is None
        or not property_file.text
        or Path(property_file.text.replace("\\", "/")).parts[-3:]
        != Path(suffix).parts
    ):
      raise RuntimeError("formal recovery migration property path is invalid")
    include.text = str(
        definition.parent / f"hard-case-candidates-{name}.set"
    )
    property_file.text = str(
        (
            Path(sv_benchmarks).resolve()
            if name == "official"
            else Path(manifest_path).resolve().parent
        )
        / suffix
    )
  expected = benchmark_root(
      FORMAL_DISPLAY, "900 s", "910 s", "920 s"
  )
  ET.SubElement(expected, "resultfiles").text = "**/witness.*"
  for name, value in (
      ("--svcomp27", None),
      ("--heap", "10000M"),
      ("--benchmark", None),
      ("--timelimit", "900 s"),
  ):
    option = ET.SubElement(expected, "option", {"name": name})
    if value:
      option.text = value
  grouped_rows = {
      "official": [
          row for row in subset["tasks"] if row["source"] == "sv-benchmarks"
      ],
      "external": [
          row for row in subset["tasks"] if row["source"] != "sv-benchmarks"
      ],
  }
  groups = {
      name: definition.parent / f"hard-case-candidates-{name}.set"
      for name, rows in grouped_rows.items()
      if rows
  }
  write_run_definition(
      expected,
      "hard-case-candidates",
      groups,
      Path(sv_benchmarks).resolve() / "c/properties/unreach-call.prp",
      Path(manifest_path).resolve().parent
      / "corpus/properties/unreach-call.prp",
  )
  if xml_shape(normalized) != xml_shape(expected):
    raise RuntimeError("formal recovery migration definition topology differs")
  return tasks


def formal_recovery_shard(protocol, repetition, shard_id):
  matches = [
      shard
      for record in protocol["repetitions"]
      if record["repetition"] == repetition
      for shard in record["shards"]
      if shard["id"] == shard_id
  ]
  if len(matches) != 1:
    raise RuntimeError("formal recovery shard identity is invalid")
  return matches[0]


def next_formal_attempt_number(root, repetition):
  pattern = re.compile(
      rf"repetition-{repetition}-replacement-attempt-([1-9]\d*)"
  )
  numbers = []
  for directory in (
      Path(root) / "provenance/preparations",
      Path(root) / "provenance/authorizations",
      Path(root) / "provenance/attempts",
  ):
    if directory.exists():
      for path in directory.glob("*.json"):
        match = pattern.fullmatch(path.stem)
        if match:
          numbers.append(int(match.group(1)))
  return max(numbers, default=0) + 1


def formal_recovery_preparation(root, path, state):
  root = Path(root).resolve()
  declared = Path(path)
  path = declared.resolve()
  if (
      declared.is_symlink()
      or Path(os.path.abspath(declared)) != path
      or not path.is_file()
  ):
    raise RuntimeError("formal recovery preparation is not a regular file")
  record = json.loads(path.read_text(encoding="utf-8"))
  if (
      not isinstance(record, dict)
      or set(record) != {
          "schema_version",
          "protocol_sha256",
          "seed_ledger_sha256",
          "repetition",
          "label",
          "shard_id",
          "tasks",
          "task_set_sha256",
          "definition_files",
      }
      or record["schema_version"] != FORMAL_RECOVERY_PREPARATION_SCHEMA
      or record["protocol_sha256"] != state["protocol_sha256"]
      or record["seed_ledger_sha256"] != state["seed_sha256"]
      or record["repetition"] not in {1, 2}
      or not isinstance(record["label"], str)
      or not isinstance(record["tasks"], list)
      or record["tasks"] != sorted(record["tasks"])
      or len(set(record["tasks"])) != len(record["tasks"])
      or record["task_set_sha256"] != task_set_sha256(record["tasks"])
      or not isinstance(record["definition_files"], list)
  ):
    raise RuntimeError("formal recovery preparation is invalid")
  for entry in record["definition_files"]:
    validate_recovery_file_entry(root, entry, "preparation definition")
  return record


def command_prepare_formal_recovery_shard(args):
  root = Path(args.output_root).resolve()
  state = load_formal_recovery_ledger(
      root,
      args.protocol,
      args.seed_ledger,
      args.manifest,
      args.property_file,
      args.sv_benchmarks,
  )
  pending = state["pending"][args.repetition]
  if not pending:
    print(json.dumps({"complete": True, "repetition": args.repetition}))
    return
  pending_set = set(pending)
  shard = next(
      shard
      for shard in state["protocol"]["repetitions"][args.repetition - 1][
          "shards"
      ]
      if pending_set & set(shard["tasks"])
  )
  tasks = [task for task in shard["tasks"] if task in pending_set]
  preparations = root / "provenance/preparations"
  preparations.mkdir(parents=True, exist_ok=True)
  existing = []
  for path in preparations.glob(
      f"repetition-{args.repetition}-replacement-attempt-*.json"
  ):
    record = formal_recovery_preparation(root, path, state)
    marker = root / f"provenance/attempts/{record['label']}.json"
    ledger = root / "provenance/formal-ledger/entries"
    accepted = any(
        entry["attempt_marker"]["path"]
        == marker.relative_to(root).as_posix()
        for _, entry in state["attempts"]
    )
    abandoned = any(
        entry["label"] == record["label"]
        for entry in state["abandonments"]
    )
    rejected = any(
        entry["label"] == record["label"]
        for entry in state["rejections"]
    )
    if not accepted and not abandoned and not rejected:
      existing.append(record)
  if existing:
    if len(existing) != 1:
      raise RuntimeError("formal recovery has multiple open preparations")
    record = existing[0]
    if record["tasks"] != sorted(tasks) or record["shard_id"] != shard["id"]:
      raise RuntimeError("open formal recovery preparation differs")
    print(json.dumps({"complete": False, **record}, sort_keys=True))
    return
  number = next_formal_attempt_number(root, args.repetition)
  label = (
      f"repetition-{args.repetition}-replacement-attempt-{number}"
  )
  output = root / f"generated/{label}"
  selected = [state["manifest"][task] for task in tasks]
  namespace = argparse.Namespace(
      manifest=args.manifest,
      sv_benchmarks=args.sv_benchmarks,
      property_file=str(
          Path(args.sv_benchmarks).resolve()
          / "c/properties/unreach-call.prp"
      ),
      output_dir=str(output),
  )
  render_stock(
      namespace,
      FORMAL_DISPLAY,
      ("900 s", "910 s", "920 s"),
      rows=selected,
  )
  validate_formal_definition(
      output / "hard-case-candidates.xml",
      args.manifest,
      {"task_count": len(selected), "tasks": selected},
      args.sv_benchmarks,
  )
  record = {
      "schema_version": FORMAL_RECOVERY_PREPARATION_SCHEMA,
      "protocol_sha256": state["protocol_sha256"],
      "seed_ledger_sha256": state["seed_sha256"],
      "repetition": args.repetition,
      "label": label,
      "shard_id": shard["id"],
      "tasks": sorted(tasks),
      "task_set_sha256": task_set_sha256(tasks),
      "definition_files": [
          recovery_file_entry(path, root)
          for path in formal_definition_closure(
              output / "hard-case-candidates.xml"
          )
      ],
  }
  preparation = preparations / f"{label}.json"
  temporary = preparation.with_name(f".{preparation.name}.tmp-{os.getpid()}")
  temporary.write_text(
      json.dumps(record, indent=2, sort_keys=True) + "\n",
      encoding="utf-8",
  )
  os.replace(temporary, preparation)
  print(json.dumps({"complete": False, **record}, sort_keys=True))


def formal_recovery_authorization(root, path, state):
  root = Path(root).resolve()
  path = Path(path).resolve()
  record = json.loads(path.read_text(encoding="utf-8"))
  if (
      not isinstance(record, dict)
      or set(record) != {
          "schema_version",
          "protocol_sha256",
          "seed_ledger_sha256",
          "completion_state",
          "mode",
          "host",
          "label",
          "role",
          "repetition",
          "shard_id",
          "authorized_tasks",
          "task_set_sha256",
          "boot_id",
          "resources",
          "files",
      }
      or record["schema_version"] != FORMAL_RECOVERY_AUTHORIZATION_SCHEMA
      or record["protocol_sha256"] != state["protocol_sha256"]
      or record["seed_ledger_sha256"] != state["seed_sha256"]
      or record["completion_state"] != "prelaunch"
      or record["mode"] != state["protocol"]["mode"]
      or record["host"] != state["protocol"]["host"]
      or record["role"] != "replacement"
      or record["repetition"] not in {1, 2}
      or path.stem != record["label"]
      or not isinstance(record["authorized_tasks"], list)
      or record["authorized_tasks"] != sorted(record["authorized_tasks"])
      or len(set(record["authorized_tasks"]))
      != len(record["authorized_tasks"])
      or record["task_set_sha256"]
      != task_set_sha256(record["authorized_tasks"])
      or not re.fullmatch(
          r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
          r"[0-9a-f]{4}-[0-9a-f]{12}",
          record["boot_id"],
      )
      or record["resources"] != state["protocol"]["runtime"]
      or not isinstance(record["files"], dict)
      or set(record["files"]) != {
          "manifest",
          "protocol",
          "seed_ledger",
          "preparation",
          "definition",
          "definition_task_sets",
          "process_descriptor",
          "result_directory",
          "benchexec_log",
          "load_monitor",
          "machine_before",
      }
  ):
    raise RuntimeError("formal recovery authorization is invalid")
  validated = {}
  for label in (
      "manifest",
      "protocol",
      "seed_ledger",
      "preparation",
      "definition",
      "process_descriptor",
  ):
    validated[label] = validate_recovery_file_entry(
        root, record["files"][label], f"authorization {label}"
    )
  if not isinstance(record["files"]["definition_task_sets"], list):
    raise RuntimeError("formal recovery authorization task sets are invalid")
  task_sets = [
      validate_recovery_file_entry(
          root, entry, "authorization definition task set"
      )
      for entry in record["files"]["definition_task_sets"]
  ]
  for label in (
      "result_directory",
      "benchexec_log",
      "load_monitor",
      "machine_before",
  ):
    value = record["files"][label]
    if not isinstance(value, str):
      raise RuntimeError("formal recovery authorization path is invalid")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
      raise RuntimeError("formal recovery authorization path escapes")
  shard = formal_recovery_shard(
      state["protocol"], record["repetition"], record["shard_id"]
  )
  preparation = formal_recovery_preparation(
      root, validated["preparation"], state
  )
  definition_files = formal_definition_closure(validated["definition"])
  descriptor = load_formal_process_descriptor(
      validated["process_descriptor"],
      root,
      state["protocol"]["mode"],
      record["label"],
      state["protocol"]["host"],
  )
  expected_paths = {
      "result_directory": f"results/{record['label']}",
      "benchexec_log": f"provenance/{record['label']}-benchexec.log",
      "load_monitor": f"provenance/{record['label']}-load-monitor.jsonl",
      "machine_before": f"provenance/machine-before-{record['label']}.json",
  }
  if (
      validated["manifest"] != state["manifest_path"]
      or validated["protocol"]
      != root / "input/recovery-protocol/protocol.json"
      or validated["seed_ledger"]
      != root / "input/recovery-protocol/seed-ledger.json"
      or preparation["label"] != record["label"]
      or preparation["repetition"] != record["repetition"]
      or preparation["shard_id"] != record["shard_id"]
      or preparation["tasks"] != record["authorized_tasks"]
      or record["authorized_tasks"]
      != sorted(task for task in shard["tasks"] if task in preparation["tasks"])
      or record["files"]["definition"]
      != preparation["definition_files"][0]
      or record["files"]["definition_task_sets"]
      != preparation["definition_files"][1:]
      or definition_files != [validated["definition"], *task_sets]
      or sorted(definition_manifest_tasks(
          validated["definition"],
          state["manifest_path"],
          state["manifest"],
          state["sv_benchmarks"],
      ))
      != record["authorized_tasks"]
      or any(
          record["files"][label] != value
          for label, value in expected_paths.items()
      )
      or descriptor["inputs"]["definition"]
      != str(validated["definition"])
      or descriptor["inputs"]["result_output"]
      != str(root / expected_paths["result_directory"])
      or descriptor["inputs"]["monitor_output"]
      != str(root / expected_paths["load_monitor"])
  ):
    raise RuntimeError("formal recovery authorization closure differs")
  return record


def command_authorize_formal_recovery_attempt(args):
  root = Path(args.output_root).resolve()
  state = load_formal_recovery_ledger(
      root,
      args.protocol,
      args.seed_ledger,
      args.manifest,
      args.property_file,
      args.sv_benchmarks,
  )
  preparation_path = (
      root / f"provenance/preparations/{args.label}.json"
  )
  preparation = formal_recovery_preparation(
      root, preparation_path, state
  )
  if (
      preparation["repetition"] != args.repetition
      or preparation["label"] != args.label
  ):
    raise RuntimeError("formal recovery preparation identity differs")
  shard = formal_recovery_shard(
      state["protocol"], args.repetition, preparation["shard_id"]
  )
  pending = set(state["pending"][args.repetition])
  expected_tasks = sorted(task for task in shard["tasks"] if task in pending)
  if preparation["tasks"] != expected_tasks or not expected_tasks:
    raise RuntimeError("formal recovery authorization is not current pending work")
  definition = root / preparation["definition_files"][0]["path"]
  actual_tasks = definition_manifest_tasks(
      definition,
      args.manifest,
      state["manifest"],
      args.sv_benchmarks,
  )
  if sorted(actual_tasks) != expected_tasks:
    raise RuntimeError("formal recovery definition tasks differ")
  descriptor = load_formal_process_descriptor(
      args.process_descriptor,
      root,
      state["protocol"]["mode"],
      args.label,
      state["protocol"]["host"],
  )
  if (
      descriptor["inputs"]["definition"] != str(definition)
      or descriptor["inputs"]["result_output"]
      != str(root / f"results/{args.label}")
  ):
    raise RuntimeError("formal recovery process descriptor paths differ")
  files = {
      "manifest": recovery_file_entry(args.manifest, root),
      "protocol": recovery_file_entry(args.protocol, root),
      "seed_ledger": recovery_file_entry(args.seed_ledger, root),
      "preparation": recovery_file_entry(preparation_path, root),
      "definition": recovery_file_entry(definition, root),
      "definition_task_sets": [
          recovery_file_entry(path, root)
          for path in formal_definition_closure(definition)[1:]
      ],
      "process_descriptor": recovery_file_entry(
          args.process_descriptor, root
      ),
      "result_directory": f"results/{args.label}",
      "benchexec_log": f"provenance/{args.label}-benchexec.log",
      "load_monitor": f"provenance/{args.label}-load-monitor.jsonl",
      "machine_before": f"provenance/machine-before-{args.label}.json",
  }
  record = {
      "schema_version": FORMAL_RECOVERY_AUTHORIZATION_SCHEMA,
      "protocol_sha256": state["protocol_sha256"],
      "seed_ledger_sha256": state["seed_sha256"],
      "completion_state": "prelaunch",
      "mode": state["protocol"]["mode"],
      "host": state["protocol"]["host"],
      "label": args.label,
      "role": "replacement",
      "repetition": args.repetition,
      "shard_id": preparation["shard_id"],
      "authorized_tasks": expected_tasks,
      "task_set_sha256": task_set_sha256(expected_tasks),
      "boot_id": read_boot_id(),
      "resources": state["protocol"]["runtime"],
      "files": files,
  }
  output = root / f"provenance/authorizations/{args.label}.json"
  content = json.dumps(record, indent=2, sort_keys=True) + "\n"
  if output.exists():
    if output.is_symlink() or output.read_text(encoding="utf-8") != content:
      raise RuntimeError("formal recovery authorization already differs")
  else:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, output)
  formal_recovery_authorization(root, output, state)
  print(output)


def formal_recovery_abandonment(root, path, state):
  root = Path(root).resolve()
  path = Path(path).resolve()
  record = json.loads(path.read_text(encoding="utf-8"))
  if (
      not isinstance(record, dict)
      or set(record) != {
          "schema_version",
          "protocol_sha256",
          "seed_ledger_sha256",
          "completion_state",
          "label",
          "benchexec_exit",
          "recovery_boot_id",
          "authorization",
          "files",
      }
      or record["schema_version"] != FORMAL_RECOVERY_ABANDONMENT_SCHEMA
      or record["protocol_sha256"] != state["protocol_sha256"]
      or record["seed_ledger_sha256"] != state["seed_sha256"]
      or record["completion_state"] != "pre_task_failure"
      or path.stem != record["label"]
      or (
          record["benchexec_exit"] is not None
          and (
              not isinstance(record["benchexec_exit"], int)
              or record["benchexec_exit"] == 0
          )
      )
      or not re.fullmatch(
          r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
          r"[0-9a-f]{4}-[0-9a-f]{12}",
          record["recovery_boot_id"],
      )
      or not isinstance(record["files"], dict)
      or set(record["files"]) != {
          "process_descriptor",
          "benchexec_log",
          "benchexec_process",
          "load_monitor",
          "monitor_pid",
          "monitor_process",
          "monitor_stopped",
          "machine_before",
          "machine_after",
          "machine_check",
      }
  ):
    raise RuntimeError("formal recovery pre-task abandonment is invalid")
  authorization_path = validate_recovery_file_entry(
      root, record["authorization"], "abandonment authorization"
  )
  authorization = formal_recovery_authorization(
      root, authorization_path, state
  )
  if authorization["label"] != record["label"]:
    raise RuntimeError("formal recovery abandonment authorization differs")
  files = {}
  for label, entry in record["files"].items():
    if entry is None:
      if label == "process_descriptor":
        raise RuntimeError("formal recovery abandonment evidence is missing")
      files[label] = None
    else:
      files[label] = validate_recovery_file_entry(
          root, entry, f"abandonment {label}"
      )
  if files["benchexec_log"] is not None and re.search(
      r"^\d{2}:\d{2}:\d{2}\s+starting\s+",
      files["benchexec_log"].read_text(encoding="utf-8"),
      re.MULTILINE,
  ):
    raise RuntimeError("formal recovery abandonment started a task")
  result_directory = root / authorization["files"]["result_directory"]
  if (
      result_directory.is_symlink()
      or not result_directory.is_dir()
      or any(result_directory.iterdir())
      or (root / f"provenance/attempts/{record['label']}.json").exists()
  ):
    raise RuntimeError("formal recovery abandonment has benchmark output")
  descriptor = load_formal_process_descriptor(
      files["process_descriptor"],
      root,
      state["protocol"]["mode"],
      record["label"],
      state["protocol"]["host"],
  )
  machine_paths = [
      files[label]
      for label in ("machine_before", "machine_after", "machine_check")
  ]
  same_boot = record["recovery_boot_id"] == authorization["boot_id"]
  if same_boot and any(machine_paths) and not all(machine_paths):
    raise RuntimeError(
        "same-boot formal recovery abandonment machine evidence is partial"
    )
  if all(machine_paths):
    expected_check = machine_check_record(
        files["machine_before"], files["machine_after"]
    )
    actual_check = json.loads(
        files["machine_check"].read_text(encoding="utf-8")
    )
    if (
        expected_check != actual_check
        or expected_check["hostname"] != state["protocol"]["host"]
    ):
      raise RuntimeError("formal recovery abandonment machine evidence differs")
  if (
      same_boot
      and files["benchexec_process"] is None
      and files["monitor_process"] is None
  ):
    raise RuntimeError(
        "same-boot formal recovery abandonment lacks owned process evidence"
    )
  if files["benchexec_process"] is not None:
    if files["benchexec_log"] is None:
      raise RuntimeError("formal recovery abandonment lacks launcher log")
    benchexec_identity = load_attempt_process_identity(
        files["benchexec_process"], root, record["label"]
    )
    if benchexec_identity.get("boot_id") != authorization["boot_id"]:
      raise RuntimeError("formal recovery abandonment launcher boot differs")
    validate_formal_process_identity(benchexec_identity, {
        "role": "benchexec-launcher",
        **descriptor["identities"]["benchexec-launcher"],
    })
    require_process_gone(
        benchexec_identity, descriptor["systemd_unit"]
    )
  monitor_paths = [
      files[label]
      for label in ("load_monitor", "monitor_pid", "monitor_process")
  ]
  if any(monitor_paths) and not all(monitor_paths):
    raise RuntimeError("formal recovery abandonment monitor evidence is partial")
  if all(monitor_paths):
    load_formal_contention_intervals(
        files["load_monitor"], allow_trailing_nul=True
    )
    pid_text = files["monitor_pid"].read_text(encoding="utf-8").strip()
    if not pid_text.isdigit():
      raise RuntimeError("formal recovery abandonment monitor PID is invalid")
    monitor_identity = load_attempt_process_identity(
        files["monitor_process"], root, record["label"]
    )
    if (
        monitor_identity.get("pid") != int(pid_text)
        or monitor_identity.get("boot_id") != authorization["boot_id"]
    ):
      raise RuntimeError("formal recovery abandonment monitor identity differs")
    validate_formal_process_identity(monitor_identity, {
        "role": "load-monitor",
        **descriptor["identities"]["load-monitor"],
    })
    require_process_gone(monitor_identity)
    if files["monitor_stopped"] is not None:
      entries = [
          line.split("=", 1)
          for line in files["monitor_stopped"].read_text(
              encoding="utf-8"
          ).splitlines()
          if line.count("=") == 1
      ]
      stopped = dict(entries)
      if (
          len(entries) != 3
          or stopped != {
              "pid": pid_text,
              "exit": "0",
              "samples": stopped.get("samples"),
          }
          or not stopped["samples"].isdigit()
          or int(stopped["samples"]) < 1
      ):
        raise RuntimeError(
            "formal recovery abandonment monitor stop is invalid"
        )
  elif files["monitor_stopped"] is not None:
    raise RuntimeError("formal recovery abandonment has orphan monitor stop")
  return record


def command_abandon_formal_recovery_pretask(args):
  root = Path(args.output_root).resolve()
  state = load_formal_recovery_ledger(
      root,
      args.protocol,
      args.seed_ledger,
      args.manifest,
      args.property_file,
      args.sv_benchmarks,
  )
  authorization_path = (
      root / f"provenance/authorizations/{args.label}.json"
  )
  authorization = formal_recovery_authorization(
      root, authorization_path, state
  )
  files = {
      label: (
          None
          if value is None
          else recovery_file_entry(value, root)
      )
      for label, value in {
          "process_descriptor": args.process_descriptor,
          "benchexec_log": args.benchexec_log,
          "benchexec_process": args.benchexec_process,
          "load_monitor": args.load_monitor,
          "monitor_pid": args.monitor_pid,
          "monitor_process": args.monitor_process,
          "monitor_stopped": args.monitor_stopped,
          "machine_before": args.machine_before,
          "machine_after": args.machine_after,
          "machine_check": args.machine_check,
      }.items()
  }
  record = {
      "schema_version": FORMAL_RECOVERY_ABANDONMENT_SCHEMA,
      "protocol_sha256": state["protocol_sha256"],
      "seed_ledger_sha256": state["seed_sha256"],
      "completion_state": "pre_task_failure",
      "label": args.label,
      "benchexec_exit": args.benchexec_exit,
      "recovery_boot_id": read_boot_id(),
      "authorization": recovery_file_entry(authorization_path, root),
      "files": files,
  }
  if authorization["label"] != args.label:
    raise RuntimeError("formal recovery abandonment label differs")
  output = root / f"provenance/formal-ledger/abandonments/{args.label}.json"
  if output.exists() or output.is_symlink():
    raise RuntimeError("formal recovery abandonment already exists")
  output.parent.mkdir(parents=True, exist_ok=True)
  temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
  temporary.write_text(
      json.dumps(record, indent=2, sort_keys=True) + "\n",
      encoding="utf-8",
  )
  os.replace(temporary, output)
  formal_recovery_abandonment(root, output, state)
  print(output)


def classify_formal_recovery_row(row, tainted):
  if row is None or not row_is_complete(row):
    return "structurally_incomplete", False
  if tainted:
    return "complete_but_tainted", False
  if row["category"] == "correct" or is_analysis_unsolved(row):
    return "accepted_and_reusable", True
  return "verifier_failure", True


def record_formal_recovery_rejection(
    root, state, authorization_path, authorization, error
):
  message = str(error)
  record = {
      "schema_version": FORMAL_RECOVERY_REJECTION_SCHEMA,
      "protocol_sha256": state["protocol_sha256"],
      "seed_ledger_sha256": state["seed_sha256"],
      "completion_state": "invalid_evidence",
      "label": authorization["label"],
      "authorization": recovery_file_entry(authorization_path, root),
      "error": message,
      "error_sha256": sha256_text(message),
      "rows": [
          {
              "task": task,
              "classification": "invalid_evidence",
              "settled": False,
          }
          for task in authorization["authorized_tasks"]
      ],
  }
  output = (
      Path(root)
      / f"provenance/formal-ledger/rejections/{authorization['label']}.json"
  )
  if output.exists() or output.is_symlink():
    raise RuntimeError("formal recovery rejection already exists")
  output.parent.mkdir(parents=True, exist_ok=True)
  temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
  temporary.write_text(
      json.dumps(record, indent=2, sort_keys=True) + "\n",
      encoding="utf-8",
  )
  os.replace(temporary, output)
  return output


def command_accept_formal_recovery_attempt(args):
  root = Path(args.output_root).resolve()
  state = load_formal_recovery_ledger(
      root,
      args.protocol,
      args.seed_ledger,
      args.manifest,
      args.property_file,
      args.sv_benchmarks,
  )
  authorization_path = (
      root / f"provenance/authorizations/{args.label}.json"
  )
  authorization = formal_recovery_authorization(
      root, authorization_path, state
  )
  try:
    marker_path = root / f"provenance/attempts/{args.label}.json"
    marker = validate_formal_attempt_marker(
        marker_path,
        root,
        Path(args.manifest).resolve(),
        args.sv_benchmarks,
        state["protocol"]["host"],
        state["protocol"]["mode"],
    )
    if (
        marker["repetition"] != authorization["repetition"]
        or marker["role"] != "replacement"
        or not set(marker["result_tasks"])
        <= set(authorization["authorized_tasks"])
    ):
      raise RuntimeError("formal recovery marker exceeds authorization")
    taint_path = Path(args.taint_manifest).resolve()
    marker_entry = recovery_file_entry(marker_path, root)
    taint_entry = recovery_file_entry(taint_path, root)
    rows = formal_recovery_ledger_rows(
        root,
        authorization,
        marker,
        taint_entry,
        state["manifest"],
    )
  except (RuntimeError, OSError, ValueError, ET.ParseError) as error:
    record_formal_recovery_rejection(
        root, state, authorization_path, authorization, error
    )
    raise
  for row in rows:
    row["provenance"]["attempt_marker"] = marker_entry
  entry = {
      "schema_version": FORMAL_RECOVERY_LEDGER_SCHEMA,
      "protocol_sha256": state["protocol_sha256"],
      "seed_ledger_sha256": state["seed_sha256"],
      "authorization": recovery_file_entry(authorization_path, root),
      "attempt_marker": marker_entry,
      "taint_manifest": taint_entry,
      "repetition": authorization["repetition"],
      "shard_id": authorization["shard_id"],
      "rows": rows,
  }
  entries = root / "provenance/formal-ledger/entries"
  entries.mkdir(parents=True, exist_ok=True)
  output = entries / f"{marker_entry['sha256']}.json"
  content = json.dumps(entry, indent=2, sort_keys=True) + "\n"
  if output.exists():
    if output.is_symlink() or output.read_text(encoding="utf-8") != content:
      raise RuntimeError("formal recovery ledger entry already differs")
  else:
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
      target.write(content)
      target.flush()
      os.fsync(target.fileno())
    os.replace(temporary, output)
    directory = os.open(entries, os.O_RDONLY)
    try:
      os.fsync(directory)
    finally:
      os.close(directory)
  load_formal_recovery_ledger(
      root,
      args.protocol,
      args.seed_ledger,
      args.manifest,
      args.property_file,
      args.sv_benchmarks,
  )
  print(output)


def command_formal_recovery_state(args):
  state = load_formal_recovery_ledger(
      args.output_root,
      args.protocol,
      args.seed_ledger,
      args.manifest,
      args.property_file,
      args.sv_benchmarks,
  )
  print(json.dumps({
      "schema_version": "hard-case-formal-recovery-state-v1",
      "protocol_sha256": state["protocol_sha256"],
      "seed_ledger_sha256": state["seed_sha256"],
      "settled": {
          str(repetition): sum(
              candidate_repetition == repetition
              for candidate_repetition, _ in state["settled"]
          )
          for repetition in (1, 2)
      },
      "pending": {
          str(repetition): len(state["pending"][repetition])
          for repetition in (1, 2)
      },
      "pending_task_set_sha256": {
          str(repetition): task_set_sha256(state["pending"][repetition])
          for repetition in (1, 2)
      },
      "attempt_entries": len(state["attempts"]),
      "invalid_evidence_attempts": len(state["rejections"]),
  }, sort_keys=True))


def formal_recovery_plan_record(state, root, repetition):
  if state["pending"][repetition]:
    raise RuntimeError("formal recovery repetition still has pending tasks")
  rows = []
  for task in state["manifest"]:
    entry = state["settled"].get((repetition, task))
    if entry is None:
      raise RuntimeError("formal recovery repetition lacks a settled row")
    rows.append(entry)
  ledger_entries = [
      recovery_file_entry(path, root)
      for path, entry in state["attempts"]
      if entry["repetition"] == repetition
  ]
  return {
      "schema_version": FORMAL_RECOVERY_PLAN_SCHEMA,
      "protocol_sha256": state["protocol_sha256"],
      "seed_ledger_sha256": state["seed_sha256"],
      "repetition": repetition,
      "ledger_entries": ledger_entries,
      "rows": rows,
  }


def command_export_formal_recovery_plan(args):
  root = Path(args.output_root).resolve()
  state = load_formal_recovery_ledger(
      root,
      args.protocol,
      args.seed_ledger,
      args.manifest,
      args.property_file,
      args.sv_benchmarks,
  )
  record = formal_recovery_plan_record(state, root, args.repetition)
  output = Path(args.output).resolve()
  try:
    output.relative_to(root)
  except ValueError as error:
    raise RuntimeError("formal recovery plan escapes output root") from error
  if output.exists() or output.is_symlink():
    raise RuntimeError("formal recovery plan output already exists")
  output.write_text(
      json.dumps(record, indent=2, sort_keys=True) + "\n",
      encoding="utf-8",
  )
  print(output)


def load_formal_recovery_plan(path, sv_benchmarks):
  path = Path(path).resolve()
  root = path.parent
  protocol_root = root / "input/recovery-protocol"
  state = load_formal_recovery_ledger(
      root,
      protocol_root / "protocol.json",
      protocol_root / "seed-ledger.json",
      protocol_root / "candidate-manifest.json",
      protocol_root / "unreach-call.prp",
      sv_benchmarks,
  )
  record = json.loads(path.read_text(encoding="utf-8"))
  repetition = record.get("repetition") if isinstance(record, dict) else None
  if repetition not in {1, 2}:
    raise RuntimeError("formal recovery plan repetition is invalid")
  expected = formal_recovery_plan_record(state, root, repetition)
  if record != expected:
    raise RuntimeError("formal recovery plan content differs")
  result_entries = {}
  row_sources = []
  rows = {}
  for entry in record["rows"]:
    row = entry["row"]
    if not row_is_complete(row):
      raise RuntimeError("formal recovery plan contains an incomplete row")
    task = entry["task"]
    rows[task] = row
    provenance = entry["provenance"]
    result = provenance["result"]
    result_entries.setdefault(result["path"], result)
    row_sources.append({
        "task": task,
        "source": "formal_recovery_ledger",
        "classification": entry["classification"],
        **provenance,
    })
  metadata = []
  result_hashes = []
  for relative, entry in sorted(result_entries.items()):
    result = validate_recovery_file_entry(
        root, entry, "formal recovery plan result"
    )
    parsed = result_metadata(
        result, FORMAL_DISPLAY, "900 s", allow_incomplete=True
    )
    if parsed["host"] != state["protocol"]["host"]:
      raise RuntimeError("formal recovery plan result host differs")
    metadata.append(parsed)
    result_hashes.append(entry["sha256"])
  if not result_hashes:
    raise RuntimeError("formal recovery plan has no result artifacts")
  for field in ("starttime", "benchmarkname"):
    if len({item[field] for item in metadata}) != len(metadata):
      raise RuntimeError(
          f"formal recovery attempts must have distinct {field} values"
      )
  return {
      "generic_recovery": True,
      "repetition": repetition,
      "plan_sha256": baseline.sha256_file(path),
      "primary_sha256": result_hashes[0],
      "taint_sha256": None,
      "replacement_sha256": result_hashes[1:],
      "metadata": metadata[0],
      "replacement_metadata": metadata[1:],
      "rows": rows,
      "row_sources": row_sources,
  }


def load_repetition_plan(
    path,
    manifest,
    manifest_path,
    host,
    sv_benchmarks,
    benchmark_definition,
    hard_threshold,
    plan_schema=FORMAL_REPETITION_PLAN_SCHEMA,
    taint_schema=FORMAL_TAINT_SCHEMA,
    display=FORMAL_DISPLAY,
    time_limit="900 s",
    definition_validator=validate_formal_definition,
):
  declared_path = Path(path)
  path = declared_path.resolve()
  if (
      declared_path.is_symlink()
      or Path(os.path.abspath(declared_path)) != path
      or not path.is_file()
  ):
    raise RuntimeError("repetition plan must be a regular non-symlink file")
  plan = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(plan, dict) or set(plan) != {
      "schema_version",
      "repetition",
      "primary",
      "taint",
      "replacements",
  }:
    raise RuntimeError("formal repetition-plan topology is not exact")
  if (
      plan["schema_version"] != plan_schema
      or not isinstance(plan["repetition"], int)
      or plan["repetition"] not in {1, 2}
      or not isinstance(plan["replacements"], list)
  ):
    raise RuntimeError("formal repetition-plan identity is invalid")
  root = path.parent
  primary = declared_plan_file(root, plan["primary"], "primary result")
  primary_hash = plan["primary"]["sha256"]
  primary_metadata = (
      probe_result_metadata(primary, allow_incomplete=True)
      if display == PROBE_DISPLAY
      else result_metadata(
          primary, display, time_limit, allow_incomplete=True
      )
  )
  if primary_metadata["host"] != host:
    raise RuntimeError("formal primary result must run on the merged manifest host")
  validate_result_run_topology(
      primary,
      manifest,
      sv_benchmarks,
      benchmark_definition,
  )
  primary_rows = {
      row["task"]: row
      for row in baseline.parse_result_rows(
          primary, manifest, hard_threshold
      )
  }

  taint_entry = plan["taint"]
  if taint_entry is None:
    tainted = {}
    taint_hash = None
  else:
    taint_path = declared_plan_file(root, taint_entry, "taint manifest")
    taint_hash = taint_entry["sha256"]
    tainted = validate_taint_manifest(
        json.loads(taint_path.read_text(encoding="utf-8")),
        plan["repetition"],
        primary_hash,
        manifest,
        taint_schema,
    )
  missing = {
      task for task, row in primary_rows.items() if not row_is_complete(row)
  }
  if missing - set(tainted):
    raise RuntimeError(
        f"incomplete primary rows are not tainted: {sorted(missing - set(tainted))}"
    )

  accepted = dict(primary_rows)
  row_sources = {
      task: {
          "task": task,
          "source": "primary",
          "result_path": plan["primary"]["path"],
          "result_sha256": primary_hash,
      }
      for task in manifest
  }
  replacement_tasks = set()
  replacement_hashes = []
  replacement_metadata = []
  previous_path = ""
  for entry in plan["replacements"]:
    if (
        not isinstance(entry, dict)
        or set(entry) != {
            "path",
            "sha256",
            "definition_path",
            "definition_sha256",
            "tasks",
        }
        or not isinstance(entry["path"], str)
        or not isinstance(entry["sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        or not isinstance(entry["definition_path"], str)
        or not isinstance(entry["definition_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", entry["definition_sha256"])
        or not isinstance(entry["tasks"], list)
        or not entry["tasks"]
        or any(not isinstance(task, str) for task in entry["tasks"])
        or entry["tasks"] != sorted(entry["tasks"])
        or len(entry["tasks"]) != len(set(entry["tasks"]))
        or entry["path"] <= previous_path
    ):
      raise RuntimeError("formal replacement entry is invalid or not sorted")
    previous_path = entry["path"]
    tasks = set(entry["tasks"])
    if not tasks <= set(tainted) or tasks & replacement_tasks:
      raise RuntimeError("formal replacement tasks are untainted or duplicated")
    replacement = declared_plan_file(root, {
        "path": entry["path"],
        "sha256": entry["sha256"],
    }, "replacement result")
    if sorted(result_task_names(replacement, manifest)) != entry["tasks"]:
      raise RuntimeError("replacement result tasks do not match its plan entry")
    subset = {task: manifest[task] for task in entry["tasks"]}
    definition = declared_plan_file(
        root,
        {
            "path": entry["definition_path"],
            "sha256": entry["definition_sha256"],
        },
        "replacement definition",
    )
    full_manifest = {
        "task_count": len(entry["tasks"]),
        "tasks": [manifest[task] for task in entry["tasks"]],
    }
    definition_validator(
        definition,
        manifest_path,
        full_manifest,
        sv_benchmarks,
    )
    metadata = result_metadata(replacement, display, time_limit)
    if metadata["host"] != host:
      raise RuntimeError("formal replacement must run on the merged manifest host")
    validate_result_run_topology(
        replacement,
        subset,
        sv_benchmarks,
        definition,
    )
    rows = baseline.parse_result_rows(replacement, subset, hard_threshold)
    if any(not row_is_complete(row) for row in rows):
      raise RuntimeError("formal replacement result has incomplete rows")
    for row in rows:
      accepted[row["task"]] = row
      row_sources[row["task"]] = {
          "task": row["task"],
          "source": "replacement",
          "result_path": entry["path"],
          "result_sha256": entry["sha256"],
          "definition_path": entry["definition_path"],
          "definition_sha256": entry["definition_sha256"],
          "reason": tainted[row["task"]],
      }
    replacement_tasks.update(tasks)
    replacement_hashes.append(entry["sha256"])
    replacement_metadata.append(metadata)
  if replacement_tasks != set(tainted):
    raise RuntimeError(
        "formal replacements do not cover exactly the tainted task set"
    )
  if any(
      not row_is_complete(row)
      for task, row in accepted.items()
      if task not in replacement_tasks
  ):
    raise RuntimeError("accepted primary rows are incomplete")
  result_hashes = [primary_hash, *replacement_hashes]
  if len(result_hashes) != len(set(result_hashes)):
    raise RuntimeError("formal primary and replacement result hashes must be distinct")
  all_metadata = [primary_metadata, *replacement_metadata]
  for field in ("starttime", "benchmarkname"):
    if len({result[field] for result in all_metadata}) != len(all_metadata):
      raise RuntimeError(
          f"formal primary and replacements must have distinct {field} values"
      )
  return {
      "repetition": plan["repetition"],
      "plan_sha256": baseline.sha256_file(path),
      "primary_sha256": primary_hash,
      "taint_sha256": taint_hash,
      "replacement_sha256": replacement_hashes,
      "metadata": primary_metadata,
      "replacement_metadata": replacement_metadata,
      "rows": accepted,
      "row_sources": [row_sources[task] for task in sorted(row_sources)],
  }


def write_repetition_plan(
    args,
    plan_schema=FORMAL_REPETITION_PLAN_SCHEMA,
    taint_schema=FORMAL_TAINT_SCHEMA,
):
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"repetition plan output already exists: {output}")
  output.parent.mkdir(parents=True, exist_ok=True)
  manifest = baseline.load_task_manifest(args.manifest)
  primary = plan_file_entry(args.primary_result, output.parent)
  if args.taint_manifest:
    taint = plan_file_entry(args.taint_manifest, output.parent)
    tainted = validate_taint_manifest(
        json.loads(
            (output.parent / taint["path"]).read_text(encoding="utf-8")
        ),
        args.repetition,
        primary["sha256"],
        manifest,
        taint_schema,
    )
  else:
    taint = None
    tainted = {}
  replacements = []
  covered = set()
  replacement_results = args.replacement_result or []
  replacement_definitions = args.replacement_definition or []
  if len(replacement_results) != len(replacement_definitions):
    raise RuntimeError(
        "replacement results and definitions must have the same count"
    )
  for replacement_path, definition_path in zip(
      replacement_results, replacement_definitions, strict=True
  ):
    entry = plan_file_entry(replacement_path, output.parent)
    definition = plan_file_entry(definition_path, output.parent)
    tasks = sorted(result_task_names(replacement_path, manifest))
    if not tasks or set(tasks) & covered:
      raise RuntimeError("replacement result tasks must be nonempty and disjoint")
    covered.update(tasks)
    replacements.append(
        {
            **entry,
            "definition_path": definition["path"],
            "definition_sha256": definition["sha256"],
            "tasks": tasks,
        }
    )
  replacements.sort(key=lambda entry: entry["path"])
  if covered != set(tainted):
    raise RuntimeError("replacement results do not cover exactly the taint manifest")
  plan = {
      "schema_version": plan_schema,
      "repetition": args.repetition,
      "primary": primary,
      "taint": taint,
      "replacements": replacements,
  }
  output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
  print(output)


def command_repetition_plan(args):
  write_repetition_plan(args)


def write_iterative_repetition_plan(args, plan_schema, taint_schema):
  output = Path(args.output).resolve()
  if output.exists():
    raise RuntimeError(f"screen plan output already exists: {output}")
  output.parent.mkdir(parents=True, exist_ok=True)
  manifest = baseline.load_task_manifest(args.manifest)
  primary = plan_file_entry(args.primary_result, output.parent)
  if args.taint_manifest:
    taint = plan_file_entry(args.taint_manifest, output.parent)
    remaining = validate_taint_manifest(
        json.loads(
            (output.parent / taint["path"]).read_text(encoding="utf-8")
        ),
        args.repetition,
        primary["sha256"],
        manifest,
        taint_schema,
    )
  else:
    taint = None
    remaining = {}
  results = args.replacement_result or []
  definitions = args.replacement_definition or []
  taints = args.replacement_taint_manifest or []
  if len({len(results), len(definitions), len(taints)}) != 1:
    raise RuntimeError(
        "screen replacement results, definitions, and taints must align"
    )
  replacements = []
  for result_path, definition_path, taint_path in zip(
      results, definitions, taints, strict=True
  ):
    result = plan_file_entry(result_path, output.parent)
    definition = plan_file_entry(definition_path, output.parent)
    replacement_taint = plan_file_entry(taint_path, output.parent)
    result_tasks = sorted(result_task_names(result_path, manifest))
    if set(result_tasks) != set(remaining):
      raise RuntimeError(
          "screen replacement must contain exactly the preceding tainted tasks"
      )
    next_remaining = validate_taint_manifest(
        json.loads(
            (output.parent / replacement_taint["path"]).read_text(
                encoding="utf-8"
            )
        ),
        args.repetition,
        result["sha256"],
        manifest,
        taint_schema,
    )
    if not set(next_remaining) <= set(remaining):
      raise RuntimeError("screen replacement taint expands the pending task set")
    accepted = sorted(set(remaining) - set(next_remaining))
    replacements.append({
        **result,
        "definition_path": definition["path"],
        "definition_sha256": definition["sha256"],
        "taint_path": replacement_taint["path"],
        "taint_sha256": replacement_taint["sha256"],
        "result_tasks": result_tasks,
        "accepted_tasks": accepted,
    })
    remaining = next_remaining
  if remaining:
    raise RuntimeError("screen replacements do not resolve every tainted task")
  plan = {
      "schema_version": plan_schema,
      "repetition": args.repetition,
      "primary": primary,
      "taint": taint,
      "replacements": replacements,
  }
  output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
  print(output)


def command_screen_plan(args):
  write_iterative_repetition_plan(
      args, SCREEN_REPETITION_PLAN_SCHEMA, SCREEN_TAINT_SCHEMA
  )


def command_cap16_repetition_plan(args):
  write_iterative_repetition_plan(
      args, CAP16_FORMAL_REPETITION_PLAN_SCHEMA, FORMAL_TAINT_SCHEMA
  )


def command_cap16_probe_plan(args):
  write_iterative_repetition_plan(
      args, CAP16_PROBE_PLAN_SCHEMA, CAP16_PROBE_TAINT_SCHEMA
  )


def command_cap8_probe_plan(args):
  write_iterative_repetition_plan(
      args, CAP8_PROBE_PLAN_SCHEMA, CAP8_PROBE_TAINT_SCHEMA
  )


def load_screen_plan(
    path,
    manifest,
    manifest_path,
    host,
    sv_benchmarks,
    benchmark_definition,
    plan_schema=SCREEN_REPETITION_PLAN_SCHEMA,
    repetition=1,
    display=DISCOVERY_DISPLAY,
    time_limit="120 s",
    taint_schema=SCREEN_TAINT_SCHEMA,
    definition_validator=validate_screen_definition,
    hard_threshold=200,
):
  declared_path = Path(path)
  path = declared_path.resolve()
  if (
      declared_path.is_symlink()
      or Path(os.path.abspath(declared_path)) != path
      or not path.is_file()
  ):
    raise RuntimeError("screen plan must be a regular non-symlink file")
  plan = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(plan, dict) or set(plan) != {
      "schema_version",
      "repetition",
      "primary",
      "taint",
      "replacements",
  } or (
      plan["schema_version"] != plan_schema
      or plan["repetition"] != repetition
      or not isinstance(plan["replacements"], list)
  ):
    raise RuntimeError("screen plan topology or identity is invalid")
  root = path.parent
  primary = declared_plan_file(root, plan["primary"], "screen primary result")
  primary_hash = plan["primary"]["sha256"]
  primary_metadata = (
      probe_result_metadata(primary, allow_incomplete=True)
      if display == PROBE_DISPLAY
      else result_metadata(
          primary, display, time_limit, allow_incomplete=True
      )
  )
  if primary_metadata["host"] != host:
    raise RuntimeError("screen primary result does not match its manifest host")
  validate_result_run_topology(
      primary, manifest, sv_benchmarks, benchmark_definition
  )
  primary_rows = {
      row["task"]: row
      for row in baseline.parse_result_rows(
          primary, manifest, hard_threshold
      )
  }
  if plan["taint"] is None:
    tainted = {}
    taint_hash = None
  else:
    taint_path = declared_plan_file(
        root, plan["taint"], "screen primary taint"
    )
    taint_hash = plan["taint"]["sha256"]
    tainted = validate_taint_manifest(
        json.loads(taint_path.read_text(encoding="utf-8")),
        repetition,
        primary_hash,
        manifest,
        taint_schema,
    )
  missing = {
      task for task, row in primary_rows.items() if not row_is_complete(row)
  }
  if missing - set(tainted):
    raise RuntimeError(
        f"incomplete screen primary rows are not tainted: "
        f"{sorted(missing - set(tainted))}"
    )
  accepted = {
      task: row
      for task, row in primary_rows.items()
      if task not in tainted
  }
  row_sources = {
      task: {
          "task": task,
          "source": "primary",
          "result_path": plan["primary"]["path"],
          "result_sha256": primary_hash,
      }
      for task in accepted
  }
  remaining = set(tainted)
  pending_reasons = dict(tainted)
  result_hashes = [primary_hash]
  metadata = [primary_metadata]
  for entry in plan["replacements"]:
    if (
        not isinstance(entry, dict)
        or set(entry) != {
            "path",
            "sha256",
            "definition_path",
            "definition_sha256",
            "taint_path",
            "taint_sha256",
            "result_tasks",
            "accepted_tasks",
        }
        or not isinstance(entry["path"], str)
        or not isinstance(entry["result_tasks"], list)
        or not isinstance(entry["accepted_tasks"], list)
        or entry["result_tasks"] != sorted(entry["result_tasks"])
        or entry["accepted_tasks"] != sorted(entry["accepted_tasks"])
    ):
      raise RuntimeError("screen replacement entry is invalid")
    replacement = declared_plan_file(
        root,
        {"path": entry["path"], "sha256": entry["sha256"]},
        "screen replacement result",
    )
    definition = declared_plan_file(
        root,
        {
            "path": entry["definition_path"],
            "sha256": entry["definition_sha256"],
        },
        "screen replacement definition",
    )
    replacement_taint = declared_plan_file(
        root,
        {"path": entry["taint_path"], "sha256": entry["taint_sha256"]},
        "screen replacement taint",
    )
    if (
        set(entry["result_tasks"]) != remaining
        or sorted(result_task_names(replacement, manifest))
        != entry["result_tasks"]
    ):
      raise RuntimeError(
          "screen replacement tasks do not equal the pending task set"
      )
    subset = {task: manifest[task] for task in entry["result_tasks"]}
    replacement_manifest = {
        "task_count": len(entry["result_tasks"]),
        "tasks": [manifest[task] for task in entry["result_tasks"]],
    }
    definition_validator(
        definition,
        manifest_path,
        replacement_manifest,
        sv_benchmarks,
    )
    replacement_metadata = (
        probe_result_metadata(replacement, allow_incomplete=True)
        if display == PROBE_DISPLAY
        else result_metadata(
            replacement, display, time_limit, allow_incomplete=True
        )
    )
    if replacement_metadata["host"] != host:
      raise RuntimeError("screen replacement does not match its manifest host")
    validate_result_run_topology(
        replacement, subset, sv_benchmarks, definition
    )
    rows = {
        row["task"]: row
        for row in baseline.parse_result_rows(
            replacement, subset, hard_threshold
        )
    }
    next_tainted = validate_taint_manifest(
        json.loads(replacement_taint.read_text(encoding="utf-8")),
        repetition,
        entry["sha256"],
        manifest,
        taint_schema,
    )
    if not set(next_tainted) <= remaining:
      raise RuntimeError("screen replacement taint expands the pending task set")
    expected_accepted = sorted(remaining - set(next_tainted))
    if entry["accepted_tasks"] != expected_accepted:
      raise RuntimeError("screen replacement accepted-task set is invalid")
    if any(not row_is_complete(rows[task]) for task in expected_accepted):
      raise RuntimeError("accepted screen replacement row is incomplete")
    for task in expected_accepted:
      accepted[task] = rows[task]
      row_sources[task] = {
          "task": task,
          "source": "replacement",
          "result_path": entry["path"],
          "result_sha256": entry["sha256"],
          "definition_path": entry["definition_path"],
          "definition_sha256": entry["definition_sha256"],
          "taint_path": entry["taint_path"],
          "taint_sha256": entry["taint_sha256"],
          "reason": pending_reasons[task],
      }
    remaining = set(next_tainted)
    pending_reasons = dict(next_tainted)
    result_hashes.append(entry["sha256"])
    metadata.append(replacement_metadata)
  if remaining or set(accepted) != set(manifest):
    raise RuntimeError("screen plan does not resolve exactly the full manifest")
  if len(result_hashes) != len(set(result_hashes)):
    raise RuntimeError("screen result artifacts must be distinct")
  for field in ("starttime", "benchmarkname"):
    if len({item[field] for item in metadata}) != len(metadata):
      raise RuntimeError(f"screen attempts must have distinct {field} values")
  return {
      "repetition": repetition,
      "plan_sha256": baseline.sha256_file(path),
      "primary_sha256": primary_hash,
      "taint_sha256": taint_hash,
      "replacement_sha256": result_hashes[1:],
      "metadata": primary_metadata,
      "replacement_metadata": metadata[1:],
      "rows": accepted,
      "row_sources": [row_sources[task] for task in sorted(row_sources)],
  }


def command_summarize(args):
  require_absent_or_empty_output(args.output_dir)
  if len(args.repetition_plan) != 2:
    raise RuntimeError("Dataset classification requires exactly two frozen repetitions")
  if args.hard_threshold != 200:
    raise RuntimeError("formal hard threshold is fixed at 200 CPU seconds")
  manifest_path = Path(args.manifest).resolve()
  full_manifest, host = authenticate_formal_manifest(args)
  if not full_manifest["tasks"]:
    raise RuntimeError("formal Phase B skipped: authenticated host merge has no tasks")
  validate_formal_definition(
      args.benchmark_definition,
      manifest_path,
      full_manifest,
      args.sv_benchmarks,
  )
  manifest = baseline.load_task_manifest(manifest_path)
  plan_schemas = [
      json.loads(Path(plan).read_text(encoding="utf-8")).get(
          "schema_version"
      )
      for plan in args.repetition_plan
  ]
  if plan_schemas == [FORMAL_RECOVERY_PLAN_SCHEMA] * 2:
    plans = [
        load_formal_recovery_plan(plan, args.sv_benchmarks)
        for plan in args.repetition_plan
    ]
    if any(set(plan["rows"]) != set(manifest) for plan in plans):
      raise RuntimeError("formal recovery plans differ from the manifest")
  elif FORMAL_RECOVERY_PLAN_SCHEMA in plan_schemas:
    raise RuntimeError("formal recovery and legacy plans cannot be mixed")
  elif hasattr(args, "phase_a_output"):
    plans = [
        load_screen_plan(
            plan,
            manifest,
            manifest_path,
            host,
            args.sv_benchmarks,
            args.benchmark_definition,
            plan_schema=CAP16_FORMAL_REPETITION_PLAN_SCHEMA,
            repetition=index,
            display=FORMAL_DISPLAY,
            time_limit="900 s",
            taint_schema=FORMAL_TAINT_SCHEMA,
            definition_validator=validate_formal_definition,
            hard_threshold=args.hard_threshold,
        )
        for index, plan in enumerate(args.repetition_plan, start=1)
    ]
  else:
    plans = [
        load_repetition_plan(
          plan,
          manifest,
          manifest_path,
          host,
          args.sv_benchmarks,
          args.benchmark_definition,
          args.hard_threshold,
        )
        for plan in args.repetition_plan
    ]
  if [plan["repetition"] for plan in plans] != [1, 2]:
    raise RuntimeError("formal repetition plans must be ordered 1 then 2")
  if len({plan["plan_sha256"] for plan in plans}) != 2:
    raise RuntimeError("formal repetition plans must have distinct hashes")
  if len({plan["primary_sha256"] for plan in plans}) != 2:
    raise RuntimeError("formal repetitions must have distinct primary results")
  all_result_hashes = [
      digest
      for plan in plans
      for digest in [plan["primary_sha256"], *plan["replacement_sha256"]]
  ]
  if len(all_result_hashes) != len(set(all_result_hashes)):
    raise RuntimeError("formal result artifacts cannot be reused across repetitions")
  metadata = [
      result
      for plan in plans
      for result in [plan["metadata"], *plan["replacement_metadata"]]
  ]
  for field in ("starttime", "benchmarkname"):
    if len({result[field] for result in metadata}) != len(metadata):
      raise RuntimeError(f"formal attempts must have distinct {field} values")
  output = Path(args.output_dir)
  output.mkdir(parents=True, exist_ok=True)
  provenance = {
      "schema_version": "hard-case-formal-row-provenance-v1",
      "repetitions": [
          {
              "repetition": plan["repetition"],
              "plan_sha256": plan["plan_sha256"],
              "primary_result_sha256": plan["primary_sha256"],
              "taint_manifest_sha256": plan["taint_sha256"],
              "replacement_result_sha256": plan["replacement_sha256"],
              "rows": plan["row_sources"],
          }
          for plan in plans
      ],
  }
  provenance_path = output / "row-provenance.json"
  provenance_path.write_text(
      json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
  )
  details = {row["task"]: row for row in full_manifest["tasks"]}
  rows = []
  for task in sorted(manifest):
    runs = [plan["rows"][task] for plan in plans]
    classification = classify_repetitions(runs, args.hard_threshold)
    family = details[task]["family"]
    rows.append(
        {
            "task": task,
            "source": details[task]["source"],
            "family": family,
            "expected_verdict": manifest[task]["expected_verdict"],
            "classification": classification,
            "split": split_for_family(f"{details[task]['source']}:{family}"),
            "cpu_seconds": ";".join(str(run["cpu_time_seconds"]) for run in runs),
            "statuses": ";".join(run["status"] for run in runs),
            "result_sources": ";".join(
                next(
                    row["source"]
                    for row in plan["row_sources"]
                    if row["task"] == task
                )
                for plan in plans
            ),
        }
    )
  fieldnames = (
      list(rows[0])
      if rows
      else [
          "task",
          "source",
          "family",
          "expected_verdict",
          "classification",
          "split",
          "cpu_seconds",
          "statuses",
          "result_sources",
      ]
  )
  for filename, subset in (
      ("classification.csv", rows),
      (
          "hard-portfolio.csv",
          [
              row
              for row in rows
              if row["classification"]
              in {"stable_hard_solved", "stable_analysis_unsolved"}
          ],
      ),
      (
          "wrong-quarantine.csv",
          [row for row in rows if row["classification"] == "wrong_quarantine"],
      ),
      (
          "verifier-failure-quarantine.csv",
          [
              row
              for row in rows
              if row["classification"] == "verifier_failure_quarantine"
          ],
      ),
      ("mixed.csv", [row for row in rows if row["classification"] == "mixed"]),
  ):
    with (output / filename).open("w", newline="", encoding="utf-8") as target:
      writer = csv.DictWriter(target, fieldnames=fieldnames)
      writer.writeheader()
      writer.writerows(subset)
  counts = collections.Counter(row["classification"] for row in rows)
  summary = {
      "task_count": len(rows),
      "repetitions": 2,
      "hard_threshold_cpu_seconds": args.hard_threshold,
      "classifications": dict(sorted(counts.items())),
      "hard_portfolio": sum(
          row["classification"]
          in {"stable_hard_solved", "stable_analysis_unsolved"}
          for row in rows
      ),
      "by_source": {
          source: dict(
              sorted(
                  collections.Counter(
                      row["classification"] for row in rows if row["source"] == source
                  ).items()
              )
          )
          for source in sorted({row["source"] for row in rows})
      },
      "repetition_plan_sha256": [plan["plan_sha256"] for plan in plans],
      "primary_result_sha256": [plan["primary_sha256"] for plan in plans],
      "replacement_result_sha256": [
          plan["replacement_sha256"] for plan in plans
      ],
      "row_provenance_sha256": baseline.sha256_file(provenance_path),
      "host": host,
      "manifest_sha256": baseline.sha256_file(manifest_path),
      "benchmark_definition_sha256": baseline.sha256_file(
          Path(args.benchmark_definition)
      ),
  }
  (output / "summary.json").write_text(
      json.dumps(summary, indent=2) + "\n", encoding="utf-8"
  )


def add_phase_b_inputs(parser):
  parser.add_argument("--parent-manifest", required=True)
  parser.add_argument("--phase-a-manifest", action="append", required=True)
  parser.add_argument("--survivor-manifest", action="append", required=True)
  parser.add_argument("--phase-a-result", action="append", required=True)
  parser.add_argument("--sv-benchmarks", required=True)


def add_cap16_phase_b_input(parser):
  parser.add_argument("--phase-a-output", required=True)
  parser.add_argument("--sv-benchmarks", required=True)


def main():
  parser = argparse.ArgumentParser()
  commands = parser.add_subparsers(required=True)
  inventory = commands.add_parser("inventory")
  inventory.add_argument("--sv-benchmarks", required=True)
  inventory.add_argument("--svcomp-results", required=True)
  inventory.add_argument("--prior-results", required=True)
  inventory.add_argument("--external-root", required=True)
  inventory.add_argument("--output-dir", required=True)
  inventory.add_argument("--official-family-cap", type=int, default=1)
  inventory.add_argument("--external-family-cap", type=int, default=2)
  inventory.set_defaults(function=command_inventory)
  difference = commands.add_parser("difference")
  difference.add_argument("--manifest", required=True)
  difference.add_argument("--exclude-manifest", required=True)
  difference.add_argument("--sv-benchmarks", required=True)
  difference.add_argument("--output-dir", required=True)
  difference.add_argument(
      "--host", action="append", choices=DISCOVERY_HOSTS
  )
  difference.set_defaults(function=command_difference)
  validate_shards = commands.add_parser("validate-shards")
  validate_shards.add_argument("--manifest", required=True)
  validate_shards.add_argument("--shard-manifest", action="append", required=True)
  validate_shards.add_argument("--sv-benchmarks", required=True)
  validate_shards.add_argument(
      "--host", action="append", choices=DISCOVERY_HOSTS
  )
  validate_shards.set_defaults(function=command_validate_shards)
  reroute = commands.add_parser("reroute-cthulhu")
  reroute.add_argument("--manifest", required=True)
  reroute.add_argument("--sv-benchmarks", required=True)
  reroute.add_argument("--output-dir", required=True)
  reroute.set_defaults(function=command_reroute_cthulhu)
  validate_reroute = commands.add_parser("validate-reroute")
  validate_reroute.add_argument("--manifest", required=True)
  validate_reroute.add_argument(
      "--reroute-manifest", action="append", required=True
  )
  validate_reroute.add_argument("--sv-benchmarks", required=True)
  validate_reroute.set_defaults(function=command_validate_reroute)
  athena_recovery = commands.add_parser("athena-recovery")
  athena_recovery.add_argument("--athena-manifest", required=True)
  athena_recovery.add_argument("--athena-reroute-manifest", required=True)
  athena_recovery.add_argument("--sv-benchmarks", required=True)
  athena_recovery.add_argument("--output-dir", required=True)
  athena_recovery.set_defaults(function=command_athena_recovery)
  validate_athena_recovery = commands.add_parser(
      "validate-athena-recovery"
  )
  validate_athena_recovery.add_argument("--athena-manifest", required=True)
  validate_athena_recovery.add_argument(
      "--athena-reroute-manifest", required=True
  )
  validate_athena_recovery.add_argument("--manifest", required=True)
  validate_athena_recovery.add_argument("--sv-benchmarks", required=True)
  validate_athena_recovery.set_defaults(
      function=command_validate_athena_recovery
  )
  merge_survivors = commands.add_parser("merge-survivors")
  add_phase_b_inputs(merge_survivors)
  merge_survivors.add_argument("--output-dir", required=True)
  merge_survivors.set_defaults(function=command_merge_survivors)
  render = commands.add_parser("render")
  render.add_argument("--manifest", required=True)
  render.add_argument("--sv-benchmarks", required=True)
  render.add_argument("--property-file", required=True)
  render.add_argument("--output-dir", required=True)
  render.set_defaults(function=command_render)
  render_formal = commands.add_parser("render-formal")
  add_phase_b_inputs(render_formal)
  render_formal.add_argument("--manifest", required=True)
  render_formal.add_argument("--property-file", required=True)
  render_formal.add_argument("--output-dir", required=True)
  render_formal.set_defaults(function=command_render_formal)
  render_cap16_formal = commands.add_parser("render-cap16-formal")
  add_cap16_phase_b_input(render_cap16_formal)
  render_cap16_formal.add_argument("--manifest", required=True)
  render_cap16_formal.add_argument("--property-file", required=True)
  render_cap16_formal.add_argument("--output-dir", required=True)
  render_cap16_formal.set_defaults(function=command_render_formal)
  render_replacement = commands.add_parser("render-formal-replacement")
  add_phase_b_inputs(render_replacement)
  render_replacement.add_argument("--manifest", required=True)
  render_replacement.add_argument("--primary-result", required=True)
  render_replacement.add_argument("--taint-manifest", required=True)
  render_replacement.add_argument("--property-file", required=True)
  render_replacement.add_argument("--output-dir", required=True)
  render_replacement.set_defaults(function=command_render_formal_replacement)
  render_cap16_replacement = commands.add_parser(
      "render-cap16-formal-replacement"
  )
  add_cap16_phase_b_input(render_cap16_replacement)
  render_cap16_replacement.add_argument("--manifest", required=True)
  render_cap16_replacement.add_argument("--primary-result", required=True)
  render_cap16_replacement.add_argument("--taint-manifest", required=True)
  render_cap16_replacement.add_argument("--property-file", required=True)
  render_cap16_replacement.add_argument("--output-dir", required=True)
  render_cap16_replacement.set_defaults(
      function=command_render_formal_replacement
  )
  render_screen_replacement = commands.add_parser(
      "render-screen-replacement"
  )
  render_screen_replacement.add_argument("--manifest", required=True)
  render_screen_replacement.add_argument("--primary-result", required=True)
  render_screen_replacement.add_argument("--taint-manifest", required=True)
  render_screen_replacement.add_argument("--sv-benchmarks", required=True)
  render_screen_replacement.add_argument("--property-file", required=True)
  render_screen_replacement.add_argument("--output-dir", required=True)
  render_screen_replacement.set_defaults(
      function=command_render_screen_replacement
  )
  probe = commands.add_parser("render-probe")
  probe.add_argument("--manifest", required=True)
  probe.add_argument("--hard-portfolio", required=True)
  probe.add_argument("--sv-benchmarks", required=True)
  probe.add_argument("--property-file", required=True)
  probe.add_argument("--output-dir", required=True)
  probe.set_defaults(function=command_render_probe)
  authenticate_cap8_probe = commands.add_parser(
      "authenticate-cap8-formal-for-probe"
  )
  authenticate_cap8_probe.add_argument("--formal-output", required=True)
  authenticate_cap8_probe.add_argument("--sv-benchmarks", required=True)
  authenticate_cap8_probe.set_defaults(
      function=command_authenticate_cap8_formal_for_probe
  )
  authenticate_cap16_probe = commands.add_parser(
      "authenticate-cap16-formal-for-probe"
  )
  authenticate_cap16_probe.add_argument("--formal-output", required=True)
  authenticate_cap16_probe.add_argument("--sv-benchmarks", required=True)
  authenticate_cap16_probe.set_defaults(
      function=command_authenticate_cap16_formal_for_probe
  )
  package_cap8_probe = commands.add_parser("package-cap8-probe-input")
  package_cap8_probe.add_argument("--formal-output", required=True)
  package_cap8_probe.add_argument("--sv-benchmarks", required=True)
  package_cap8_probe.add_argument("--output-dir", required=True)
  package_cap8_probe.set_defaults(
      function=command_package_cap8_probe_input
  )
  package_cap16_probe = commands.add_parser("package-cap16-probe-input")
  package_cap16_probe.add_argument("--formal-output", required=True)
  package_cap16_probe.add_argument("--sv-benchmarks", required=True)
  package_cap16_probe.add_argument("--output-dir", required=True)
  package_cap16_probe.set_defaults(
      function=command_package_cap16_probe_input
  )
  validate_cap16_probe = commands.add_parser("validate-cap16-probe-input")
  validate_cap16_probe.add_argument("--probe-input", required=True)
  validate_cap16_probe.add_argument("--sv-benchmarks", required=True)
  validate_cap16_probe.set_defaults(
      function=command_validate_cap16_probe_input
  )
  validate_cap8_probe = commands.add_parser("validate-cap8-probe-input")
  validate_cap8_probe.add_argument("--probe-input", required=True)
  validate_cap8_probe.add_argument("--sv-benchmarks", required=True)
  validate_cap8_probe.set_defaults(
      function=command_validate_cap8_probe_input
  )
  render_cap8_probe = commands.add_parser("render-cap8-probe")
  render_cap8_probe.add_argument("--probe-input", required=True)
  render_cap8_probe.add_argument("--sv-benchmarks", required=True)
  render_cap8_probe.add_argument("--property-file", required=True)
  render_cap8_probe.add_argument("--output-dir", required=True)
  render_cap8_probe.set_defaults(function=command_render_cap8_probe)
  render_cap16_probe = commands.add_parser("render-cap16-probe")
  render_cap16_probe.add_argument("--probe-input", required=True)
  render_cap16_probe.add_argument("--sv-benchmarks", required=True)
  render_cap16_probe.add_argument("--property-file", required=True)
  render_cap16_probe.add_argument("--output-dir", required=True)
  render_cap16_probe.set_defaults(function=command_render_cap16_probe)
  render_cap16_probe_replacement = commands.add_parser(
      "render-cap16-probe-replacement"
  )
  render_cap16_probe_replacement.add_argument(
      "--probe-input", required=True
  )
  render_cap16_probe_replacement.add_argument(
      "--sv-benchmarks", required=True
  )
  render_cap16_probe_replacement.add_argument(
      "--primary-result", required=True
  )
  render_cap16_probe_replacement.add_argument(
      "--taint-manifest", required=True
  )
  render_cap16_probe_replacement.add_argument(
      "--property-file", required=True
  )
  render_cap16_probe_replacement.add_argument(
      "--output-dir", required=True
  )
  render_cap16_probe_replacement.set_defaults(
      function=command_render_cap16_probe_replacement
  )
  render_cap8_probe_replacement = commands.add_parser(
      "render-cap8-probe-replacement"
  )
  render_cap8_probe_replacement.add_argument(
      "--probe-input", required=True
  )
  render_cap8_probe_replacement.add_argument(
      "--sv-benchmarks", required=True
  )
  render_cap8_probe_replacement.add_argument(
      "--primary-result", required=True
  )
  render_cap8_probe_replacement.add_argument(
      "--taint-manifest", required=True
  )
  render_cap8_probe_replacement.add_argument(
      "--property-file", required=True
  )
  render_cap8_probe_replacement.add_argument(
      "--output-dir", required=True
  )
  render_cap8_probe_replacement.set_defaults(
      function=command_render_cap8_probe_replacement
  )
  validate = commands.add_parser("validate")
  validate.add_argument("--manifest", required=True)
  validate.add_argument("--sv-benchmarks", required=True)
  validate.set_defaults(function=command_validate)
  validate_cap16 = commands.add_parser("validate-cap16-phase-a")
  add_cap16_phase_b_input(validate_cap16)
  validate_cap16.set_defaults(function=command_validate_cap16_phase_a)
  package_cap16 = commands.add_parser("package-cap16-phase-a")
  add_cap16_phase_b_input(package_cap16)
  package_cap16.add_argument("--output-dir", required=True)
  package_cap16.set_defaults(function=command_package_cap16_phase_a)
  license_audit = commands.add_parser("license-audit")
  license_audit.add_argument("--manifest", required=True)
  license_audit.add_argument("--sv-benchmarks", required=True)
  license_audit.add_argument("--external-root", required=True)
  license_audit.add_argument("--output-dir", required=True)
  license_audit.set_defaults(function=command_license_audit)
  probe_summary = commands.add_parser("probe-summary")
  probe_summary.add_argument("--manifest", required=True)
  probe_summary.add_argument("--hard-portfolio", required=True)
  probe_summary.add_argument("--result-files", required=True)
  probe_summary.add_argument("--output-dir", required=True)
  probe_summary.set_defaults(function=command_probe_summary)
  cap16_probe_summary = commands.add_parser("cap16-probe-summary")
  cap16_probe_summary.add_argument("--probe-input", required=True)
  cap16_probe_summary.add_argument("--sv-benchmarks", required=True)
  cap16_probe_summary.add_argument(
      "--benchmark-definition", required=True
  )
  cap16_probe_summary.add_argument("--probe-plan", required=True)
  cap16_probe_summary.add_argument("--output-dir", required=True)
  cap16_probe_summary.set_defaults(function=command_cap16_probe_summary)
  cap8_probe_summary = commands.add_parser("cap8-probe-summary")
  cap8_probe_summary.add_argument("--probe-input", required=True)
  cap8_probe_summary.add_argument("--sv-benchmarks", required=True)
  cap8_probe_summary.add_argument(
      "--benchmark-definition", required=True
  )
  cap8_probe_summary.add_argument("--probe-plan", required=True)
  cap8_probe_summary.add_argument("--output-dir", required=True)
  cap8_probe_summary.set_defaults(function=command_cap8_probe_summary)
  repetition_plan = commands.add_parser("repetition-plan")
  repetition_plan.add_argument("--manifest", required=True)
  repetition_plan.add_argument("--repetition", type=int, choices=(1, 2), required=True)
  repetition_plan.add_argument("--primary-result", required=True)
  repetition_plan.add_argument("--taint-manifest")
  repetition_plan.add_argument("--replacement-result", action="append")
  repetition_plan.add_argument("--replacement-definition", action="append")
  repetition_plan.add_argument("--output", required=True)
  repetition_plan.set_defaults(function=command_repetition_plan)
  cap16_repetition_plan = commands.add_parser("cap16-repetition-plan")
  cap16_repetition_plan.add_argument("--manifest", required=True)
  cap16_repetition_plan.add_argument(
      "--repetition", type=int, choices=(1, 2), required=True
  )
  cap16_repetition_plan.add_argument("--primary-result", required=True)
  cap16_repetition_plan.add_argument("--taint-manifest")
  cap16_repetition_plan.add_argument(
      "--replacement-result", action="append"
  )
  cap16_repetition_plan.add_argument(
      "--replacement-definition", action="append"
  )
  cap16_repetition_plan.add_argument(
      "--replacement-taint-manifest", action="append"
  )
  cap16_repetition_plan.add_argument("--output", required=True)
  cap16_repetition_plan.set_defaults(
      function=command_cap16_repetition_plan
  )
  cap16_probe_plan = commands.add_parser("cap16-probe-plan")
  cap16_probe_plan.add_argument("--manifest", required=True)
  cap16_probe_plan.add_argument("--primary-result", required=True)
  cap16_probe_plan.add_argument("--taint-manifest")
  cap16_probe_plan.add_argument("--replacement-result", action="append")
  cap16_probe_plan.add_argument(
      "--replacement-definition", action="append"
  )
  cap16_probe_plan.add_argument(
      "--replacement-taint-manifest", action="append"
  )
  cap16_probe_plan.add_argument("--output", required=True)
  cap16_probe_plan.set_defaults(
      function=command_cap16_probe_plan, repetition=1
  )
  cap8_probe_plan = commands.add_parser("cap8-probe-plan")
  cap8_probe_plan.add_argument("--manifest", required=True)
  cap8_probe_plan.add_argument("--primary-result", required=True)
  cap8_probe_plan.add_argument("--taint-manifest")
  cap8_probe_plan.add_argument("--replacement-result", action="append")
  cap8_probe_plan.add_argument(
      "--replacement-definition", action="append"
  )
  cap8_probe_plan.add_argument(
      "--replacement-taint-manifest", action="append"
  )
  cap8_probe_plan.add_argument("--output", required=True)
  cap8_probe_plan.set_defaults(
      function=command_cap8_probe_plan, repetition=1
  )
  screen_plan = commands.add_parser("screen-plan")
  screen_plan.add_argument("--manifest", required=True)
  screen_plan.add_argument("--primary-result", required=True)
  screen_plan.add_argument("--taint-manifest")
  screen_plan.add_argument("--replacement-result", action="append")
  screen_plan.add_argument("--replacement-definition", action="append")
  screen_plan.add_argument("--replacement-taint-manifest", action="append")
  screen_plan.add_argument("--output", required=True)
  screen_plan.set_defaults(function=command_screen_plan, repetition=1)
  monitor_formal_load = commands.add_parser("monitor-formal-load")
  monitor_formal_load.add_argument("--output", required=True)
  monitor_formal_load.add_argument("--exclude-root", type=int, required=True)
  monitor_formal_load.set_defaults(function=command_monitor_formal_load)
  capture_process = commands.add_parser("capture-process-identity")
  capture_process.add_argument("--pid", type=int, required=True)
  capture_process.add_argument("--role", required=True)
  capture_process.add_argument("--output", required=True)
  capture_process.set_defaults(function=command_capture_process_identity)
  process_unit = commands.add_parser("formal-systemd-unit")
  process_unit.add_argument("--output-root", required=True)
  process_unit.add_argument(
      "--mode",
      choices=("cap8", "cap16", "cap8-probe", "cap16-probe"),
      required=True,
  )
  process_unit.add_argument("--label", required=True)
  process_unit.set_defaults(function=command_formal_systemd_unit)
  process_descriptor = commands.add_parser(
      "write-formal-process-descriptor"
  )
  for name in (
      "output-root",
      "mode",
      "label",
      "host",
      "name",
      "definition",
      "result-output",
      "monitor-output",
      "dataset-py",
      "cpachecker-dir",
      "benchexec-dir",
      "python-bin",
      "java-home",
      "p-cores",
      "output",
  ):
    process_descriptor.add_argument(f"--{name}", required=True)
  process_descriptor.add_argument(
      "--monitor-exclude-root", type=int, required=True
  )
  process_descriptor.set_defaults(
      function=command_write_formal_process_descriptor
  )
  require_formal_gone = commands.add_parser(
      "require-formal-process-gone"
  )
  require_formal_gone.add_argument("--descriptor", required=True)
  require_formal_gone.add_argument("--identity", required=True)
  require_formal_gone.add_argument("--output-root", required=True)
  require_formal_gone.add_argument(
      "--mode",
      choices=("cap8", "cap16", "cap8-probe", "cap16-probe"),
      required=True,
  )
  require_formal_gone.add_argument("--label", required=True)
  require_formal_gone.add_argument("--host", required=True)
  require_formal_gone.add_argument(
      "--role",
      choices=("benchexec-launcher", "load-monitor"),
      required=True,
  )
  require_formal_gone.set_defaults(
      function=command_require_formal_process_gone
  )
  attempt_complete = commands.add_parser("formal-attempt-complete")
  attempt_complete.add_argument("--output-root", required=True)
  attempt_complete.add_argument("--manifest", required=True)
  attempt_complete.add_argument("--sv-benchmarks", required=True)
  attempt_complete.add_argument("--host", required=True)
  attempt_complete.add_argument(
      "--mode",
      choices=("cap8", "cap16", "cap8-probe", "cap16-probe"),
      required=True,
  )
  attempt_complete.add_argument("--label", required=True)
  attempt_complete.add_argument(
      "--role", choices=("primary", "replacement"), required=True
  )
  attempt_complete.add_argument(
      "--repetition", type=int, choices=(1, 2), required=True
  )
  attempt_complete.add_argument(
      "--benchexec-exit", type=int, required=True
  )
  for name in (
      "definition",
      "result",
      "benchexec-log",
      "benchexec-process",
      "process-descriptor",
      "load-monitor",
      "monitor-pid",
      "monitor-process",
      "monitor-stopped",
      "machine-before",
      "machine-after",
      "machine-check",
  ):
    attempt_complete.add_argument(f"--{name}", required=True)
  attempt_complete.add_argument("--output", required=True)
  attempt_complete.set_defaults(function=command_formal_attempt_complete)
  validate_attempt = commands.add_parser("validate-formal-attempt")
  validate_attempt.add_argument("--output-root", required=True)
  validate_attempt.add_argument("--manifest", required=True)
  validate_attempt.add_argument("--sv-benchmarks", required=True)
  validate_attempt.add_argument("--host", required=True)
  validate_attempt.add_argument(
      "--mode", choices=("cap8", "cap16"), required=True
  )
  validate_attempt.add_argument("--label", required=True)
  validate_attempt.add_argument(
      "--role", choices=("primary", "replacement"), required=True
  )
  validate_attempt.add_argument(
      "--repetition", type=int, choices=(1, 2), required=True
  )
  validate_attempt.add_argument("--definition", required=True)
  validate_attempt.add_argument("--result", required=True)
  validate_attempt.add_argument("--marker", required=True)
  validate_attempt.set_defaults(function=command_validate_formal_attempt)
  recover_attempt = commands.add_parser("recover-formal-attempt")
  recover_attempt.add_argument("--output-root", required=True)
  recover_attempt.add_argument("--manifest", required=True)
  recover_attempt.add_argument("--sv-benchmarks", required=True)
  recover_attempt.add_argument("--host", required=True)
  recover_attempt.add_argument(
      "--mode", choices=("cap8", "cap16"), required=True
  )
  recover_attempt.add_argument("--label", required=True)
  recover_attempt.add_argument(
      "--role", choices=("primary", "replacement"), required=True
  )
  recover_attempt.add_argument(
      "--repetition", type=int, choices=(1, 2), required=True
  )
  recover_attempt.add_argument("--research-provenance", required=True)
  for name in (
      "definition",
      "result",
      "benchexec-log",
      "benchexec-process",
      "process-descriptor",
      "load-monitor",
      "monitor-pid",
      "monitor-process",
      "monitor-stopped",
      "machine-before",
      "machine-after",
      "machine-check",
  ):
    recover_attempt.add_argument(f"--{name}", required=True)
  recover_attempt.add_argument("--output", required=True)
  recover_attempt.set_defaults(function=command_recover_formal_attempt)
  restore_legacy_attempt = commands.add_parser(
      "restore-legacy-cap16-athena-attempt"
  )
  restore_legacy_attempt.add_argument("--output-root", required=True)
  restore_legacy_attempt.set_defaults(
      function=command_restore_legacy_cap16_athena_attempt
  )
  formal_closure = commands.add_parser("validate-formal-closure")
  formal_closure.add_argument("--output-root", required=True)
  formal_closure.add_argument("--manifest", required=True)
  formal_closure.add_argument("--benchmark-definition", required=True)
  formal_closure.add_argument("--sv-benchmarks", required=True)
  formal_closure.add_argument("--host", required=True)
  formal_closure.add_argument("--mode", choices=("cap8", "cap16"), required=True)
  formal_closure.add_argument(
      "--repetition-plan", action="append", required=True
  )
  formal_closure.add_argument("--require-complete", action="store_true")
  formal_closure.set_defaults(function=command_validate_formal_closure)
  freeze_recovery = commands.add_parser(
      "freeze-formal-recovery-protocol"
  )
  freeze_recovery.add_argument("--manifest", required=True)
  freeze_recovery.add_argument("--property-file", required=True)
  freeze_recovery.add_argument("--seed-ledger", required=True)
  freeze_recovery.add_argument("--runtime-closure", required=True)
  freeze_recovery.add_argument(
      "--source-commit", required=True
  )
  freeze_recovery.add_argument(
      "--mode", choices=("cap8", "cap16"), required=True
  )
  freeze_recovery.add_argument("--output", required=True)
  freeze_recovery.set_defaults(
      function=command_freeze_formal_recovery_protocol
  )
  build_recovery_seed = commands.add_parser(
      "build-formal-recovery-seed"
  )
  build_recovery_seed.add_argument("--output-root", required=True)
  build_recovery_seed.add_argument("--migration-manifest", required=True)
  build_recovery_seed.add_argument("--manifest", required=True)
  build_recovery_seed.add_argument("--sv-benchmarks", required=True)
  build_recovery_seed.add_argument(
      "--mode", choices=("cap8", "cap16"), required=True
  )
  build_recovery_seed.add_argument("--output", required=True)
  build_recovery_seed.set_defaults(
      function=command_build_formal_recovery_seed
  )
  prepare_recovery = commands.add_parser(
      "prepare-formal-recovery-shard"
  )
  prepare_recovery.add_argument("--output-root", required=True)
  prepare_recovery.add_argument("--protocol", required=True)
  prepare_recovery.add_argument("--seed-ledger", required=True)
  prepare_recovery.add_argument("--manifest", required=True)
  prepare_recovery.add_argument("--property-file", required=True)
  prepare_recovery.add_argument("--sv-benchmarks", required=True)
  prepare_recovery.add_argument(
      "--repetition", type=int, choices=(1, 2), required=True
  )
  prepare_recovery.set_defaults(
      function=command_prepare_formal_recovery_shard
  )
  authorize_recovery = commands.add_parser(
      "authorize-formal-recovery-attempt"
  )
  authorize_recovery.add_argument("--output-root", required=True)
  authorize_recovery.add_argument("--protocol", required=True)
  authorize_recovery.add_argument("--seed-ledger", required=True)
  authorize_recovery.add_argument("--manifest", required=True)
  authorize_recovery.add_argument("--property-file", required=True)
  authorize_recovery.add_argument("--sv-benchmarks", required=True)
  authorize_recovery.add_argument("--process-descriptor", required=True)
  authorize_recovery.add_argument("--label", required=True)
  authorize_recovery.add_argument(
      "--repetition", type=int, choices=(1, 2), required=True
  )
  authorize_recovery.set_defaults(
      function=command_authorize_formal_recovery_attempt
  )
  accept_recovery = commands.add_parser(
      "accept-formal-recovery-attempt"
  )
  accept_recovery.add_argument("--output-root", required=True)
  accept_recovery.add_argument("--protocol", required=True)
  accept_recovery.add_argument("--seed-ledger", required=True)
  accept_recovery.add_argument("--manifest", required=True)
  accept_recovery.add_argument("--property-file", required=True)
  accept_recovery.add_argument("--sv-benchmarks", required=True)
  accept_recovery.add_argument("--label", required=True)
  accept_recovery.add_argument("--taint-manifest", required=True)
  accept_recovery.set_defaults(
      function=command_accept_formal_recovery_attempt
  )
  abandon_recovery = commands.add_parser(
      "abandon-formal-recovery-pretask"
  )
  abandon_recovery.add_argument("--output-root", required=True)
  abandon_recovery.add_argument("--protocol", required=True)
  abandon_recovery.add_argument("--seed-ledger", required=True)
  abandon_recovery.add_argument("--manifest", required=True)
  abandon_recovery.add_argument("--property-file", required=True)
  abandon_recovery.add_argument("--sv-benchmarks", required=True)
  abandon_recovery.add_argument("--label", required=True)
  abandon_recovery.add_argument("--benchexec-exit", type=int)
  abandon_recovery.add_argument("--process-descriptor", required=True)
  for name in (
      "benchexec-log",
      "load-monitor",
      "monitor-pid",
      "monitor-process",
      "monitor-stopped",
      "machine-before",
      "machine-after",
      "machine-check",
  ):
    abandon_recovery.add_argument(f"--{name}")
  abandon_recovery.add_argument("--benchexec-process")
  abandon_recovery.set_defaults(
      function=command_abandon_formal_recovery_pretask
  )
  recovery_state = commands.add_parser("formal-recovery-state")
  recovery_state.add_argument("--output-root", required=True)
  recovery_state.add_argument("--protocol", required=True)
  recovery_state.add_argument("--seed-ledger", required=True)
  recovery_state.add_argument("--manifest", required=True)
  recovery_state.add_argument("--property-file", required=True)
  recovery_state.add_argument("--sv-benchmarks", required=True)
  recovery_state.set_defaults(function=command_formal_recovery_state)
  export_recovery = commands.add_parser(
      "export-formal-recovery-plan"
  )
  export_recovery.add_argument("--output-root", required=True)
  export_recovery.add_argument("--protocol", required=True)
  export_recovery.add_argument("--seed-ledger", required=True)
  export_recovery.add_argument("--manifest", required=True)
  export_recovery.add_argument("--property-file", required=True)
  export_recovery.add_argument("--sv-benchmarks", required=True)
  export_recovery.add_argument(
      "--repetition", type=int, choices=(1, 2), required=True
  )
  export_recovery.add_argument("--output", required=True)
  export_recovery.set_defaults(
      function=command_export_formal_recovery_plan
  )
  probe_closure = commands.add_parser("validate-cap16-probe-closure")
  probe_closure.add_argument("--output-root", required=True)
  probe_closure.add_argument("--sv-benchmarks", required=True)
  probe_closure.add_argument("--require-complete", action="store_true")
  probe_closure.set_defaults(
      function=command_validate_cap16_probe_closure
  )
  cap8_probe_closure = commands.add_parser(
      "validate-cap8-probe-closure"
  )
  cap8_probe_closure.add_argument("--output-root", required=True)
  cap8_probe_closure.add_argument("--sv-benchmarks", required=True)
  cap8_probe_closure.add_argument(
      "--require-complete", action="store_true"
  )
  cap8_probe_closure.set_defaults(
      function=command_validate_cap8_probe_closure
  )
  complete_sentinel = commands.add_parser("write-complete-sentinel")
  complete_sentinel.add_argument("--output", required=True)
  complete_sentinel.set_defaults(function=command_write_complete_sentinel)
  formal_taint = commands.add_parser("formal-taint")
  formal_taint.add_argument("--manifest", required=True)
  formal_taint.add_argument("--repetition", type=int, choices=(1, 2), required=True)
  formal_taint.add_argument("--result", required=True)
  formal_taint.add_argument("--benchexec-log", required=True)
  formal_taint.add_argument("--load-monitor", required=True)
  formal_taint.add_argument("--attempt-marker")
  formal_taint.add_argument("--output-root")
  formal_taint.add_argument("--sv-benchmarks")
  formal_taint.add_argument("--host")
  formal_taint.add_argument("--mode", choices=("cap8", "cap16"))
  formal_taint.add_argument("--output", required=True)
  formal_taint.set_defaults(function=command_formal_taint)
  probe_taint = commands.add_parser("probe-taint")
  probe_taint.add_argument("--manifest", required=True)
  probe_taint.add_argument("--result", required=True)
  probe_taint.add_argument("--benchexec-log", required=True)
  probe_taint.add_argument("--load-monitor", required=True)
  probe_taint.add_argument("--output", required=True)
  probe_taint.set_defaults(function=command_probe_taint)
  cap16_probe_taint = commands.add_parser("cap16-probe-taint")
  cap16_probe_taint.add_argument("--manifest", required=True)
  cap16_probe_taint.add_argument("--result", required=True)
  cap16_probe_taint.add_argument("--benchexec-log", required=True)
  cap16_probe_taint.add_argument("--load-monitor", required=True)
  cap16_probe_taint.add_argument("--output", required=True)
  cap16_probe_taint.set_defaults(function=command_probe_taint)
  cap8_probe_taint = commands.add_parser("cap8-probe-taint")
  cap8_probe_taint.add_argument("--manifest", required=True)
  cap8_probe_taint.add_argument("--result", required=True)
  cap8_probe_taint.add_argument("--benchexec-log", required=True)
  cap8_probe_taint.add_argument("--load-monitor", required=True)
  cap8_probe_taint.add_argument("--output", required=True)
  cap8_probe_taint.set_defaults(function=command_cap8_probe_taint)
  screen_taint = commands.add_parser("screen-taint")
  screen_taint.add_argument("--manifest", required=True)
  screen_taint.add_argument("--result", required=True)
  screen_taint.add_argument("--benchexec-log", required=True)
  screen_taint.add_argument("--load-monitor", required=True)
  screen_taint.add_argument("--output", required=True)
  screen_taint.set_defaults(function=command_screen_taint)
  summarize = commands.add_parser("summarize")
  add_phase_b_inputs(summarize)
  summarize.add_argument("--manifest", required=True)
  summarize.add_argument("--benchmark-definition", required=True)
  summarize.add_argument("--repetition-plan", action="append", required=True)
  summarize.add_argument("--output-dir", required=True)
  summarize.add_argument("--hard-threshold", type=float, default=200)
  summarize.set_defaults(function=command_summarize)
  summarize_cap16 = commands.add_parser("summarize-cap16-formal")
  add_cap16_phase_b_input(summarize_cap16)
  summarize_cap16.add_argument("--manifest", required=True)
  summarize_cap16.add_argument("--benchmark-definition", required=True)
  summarize_cap16.add_argument(
      "--repetition-plan", action="append", required=True
  )
  summarize_cap16.add_argument("--output-dir", required=True)
  summarize_cap16.add_argument("--hard-threshold", type=float, default=200)
  summarize_cap16.set_defaults(function=command_summarize)
  screen_summary = commands.add_parser("screen-summary")
  screen_summary.add_argument("--manifest", required=True)
  screen_summary.add_argument("--result", required=True)
  screen_summary.add_argument("--sv-benchmarks", required=True)
  screen_summary.add_argument("--phase-a-host", required=True)
  screen_summary.add_argument("--output-dir", required=True)
  screen_summary.set_defaults(function=command_screen_summary)
  screen_summary_plan = commands.add_parser("screen-summary-plan")
  screen_summary_plan.add_argument("--manifest", required=True)
  screen_summary_plan.add_argument("--benchmark-definition", required=True)
  screen_summary_plan.add_argument("--screen-plan", required=True)
  screen_summary_plan.add_argument("--sv-benchmarks", required=True)
  screen_summary_plan.add_argument("--phase-a-host", required=True)
  screen_summary_plan.add_argument("--output-dir", required=True)
  screen_summary_plan.set_defaults(function=command_screen_summary_plan)
  args = parser.parse_args()
  args.function(args)


if __name__ == "__main__":
  main()
