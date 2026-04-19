// Copyright (c) Last9, Inc.
// All rights reserved.
package k8sprocessor

import (
	"context"
	"log"

	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/plog"

	k8shelper "github.com/last9/gpu-telemetry/k8shelper"
)

type k8sInfoLogs struct {
	next consumer.Logs
	K8sProcessorBase
}

func newK8sInfoLogs(next consumer.Logs, cfg component.Config) *k8sInfoLogs {
	return &k8sInfoLogs{
		next:             next,
		K8sProcessorBase: NewK8sProcessorBase(cfg),
	}
}

func (kl *k8sInfoLogs) processLogs(ctx context.Context, logs plog.Logs) (plog.Logs, error) {
	gpu2k8s, err := k8shelper.GetGPU2K8s(kl.Config)
	if err != nil {
		log.Println("k8sprocessor: error getting GPU-to-K8s mapping:", err)
		gpu2k8s = make(map[string]k8shelper.K8sMetadata)
	}

	cloudZone, cloudRegion := extractCloudInfo(gpu2k8s)

	resourceLogsSlice := logs.ResourceLogs()
	for i := 0; i < resourceLogsSlice.Len(); i++ {
		kl.AddCloudAttrs(resourceLogsSlice.At(i).Resource().Attributes(), cloudZone, cloudRegion)
		// Attach aggregated pod names to the resource for log correlation.
		allData := k8shelper.GetGPUData(gpu2k8s)
		kl.AddK8sMetadataSlice(resourceLogsSlice.At(i).Resource().Attributes(), allData)

		scopeLogsSlice := resourceLogsSlice.At(i).ScopeLogs()
		for j := 0; j < scopeLogsSlice.Len(); j++ {
			logRecordsSlice := scopeLogsSlice.At(j).LogRecords()
			for k := 0; k < logRecordsSlice.Len(); k++ {
				kl.enrichLogRecord(logRecordsSlice.At(k), gpu2k8s)
			}
		}
	}

	return logs, nil
}

func (kl *k8sInfoLogs) enrichLogRecord(logRecord plog.LogRecord, gpu2k8s map[string]k8shelper.K8sMetadata) {
	gpuVal, hasGPU := logRecord.Attributes().Get("gpu_id")
	if !hasGPU {
		return
	}
	if meta, ok := gpu2k8s[gpuVal.AsString()]; ok {
		kl.AddK8sMetadata(logRecord.Attributes(), meta)
	}
}
