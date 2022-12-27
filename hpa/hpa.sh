#!/bin/bash

k get hpa -A -o json | jq '.items[] | {NAME:.metadata.name,UTIL:.spec.targetCPUUtilizationPercentage, MIN:.spec.minReplicas, MAX:.spec.maxReplicas, CURRENT:.status.currentReplicas}'
