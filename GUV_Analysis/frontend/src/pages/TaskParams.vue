<template>
  <div class="task-params">
    <div class="header">
      <div style="display: flex; flex-direction: column; gap: 5px;">
          <h2>Task Configuration: {{ taskId }}</h2>
          <el-tag v-if="nd2Filename" type="info" size="small">File: {{ nd2Filename }}</el-tag>
      </div>
      <el-button @click="$router.push('/tasks')">Back to List</el-button>
    </div>

    <el-tabs v-model="activeDetailTab" class="detail-tabs">
      <el-tab-pane label="概览" name="overview">
        <RunHistoryPanel
          :history="history"
          :selected-count="selectedRuns.length"
          @selection-change="handleSelectionChange"
          @view-run="viewRun"
          @delete-run="deleteRun"
          @delete-selected="deleteSelectedRuns"
        />

        <ExecutionPanel
          :params="params"
          :is-running="isRunning"
          :transfer-visible="transferVisible"
          :transfer-tag-type="transferTagType"
          :transfer-label="transferLabel"
          :transfer-state="transferState"
          :transfer-detail-text="transferDetailText"
          :transfer-percent="transferPercent"
          :transfer-progress-status="transferProgressStatus"
          :cold-archive-detail-text="coldArchiveDetailText"
          @run-debug="runDebug"
          @run-final="runFinal"
          @run-video="runVideo"
        />

        <RuntimeLogPanel
          :visible="!!(logs || isRunning || currentRunId)"
          :displayed-logs="displayedLogs"
          :current-run-id="currentRunId"
          :is-current-run-selected="isCurrentRunSelected"
          @refresh="fetchLogs"
        />

        <RunStatusResultsPanel
          :current-run-status="currentRunStatus"
          :current-run-mode="currentRunMode"
          :queue-position="queuePosition"
          :is-current-run-selected="isCurrentRunSelected"
          :video-artifacts="videoArtifacts"
          @download-all="downloadAllResults"
          @download-preview="downloadPreview"
          @download-result="downloadResult"
          @download-artifact="downloadArtifact"
        />
      </el-tab-pane>

      <el-tab-pane label="参数" name="params">
        <el-card v-loading="loading">
          <template #header>
            <div class="card-header">
              <span>MATLAB 分析参数</span>
              <div class="actions">
                 <el-dropdown split-button type="warning" @click="resetToDefaults" @command="handlePresetCommand" trigger="click">
                    Reset Defaults
                    <template #dropdown>
                        <el-dropdown-menu>
                            <el-dropdown-item command="default">Reset to System Defaults</el-dropdown-item>
                            <el-dropdown-item divided v-if="demos.length > 0" disabled>Preset Demos:</el-dropdown-item>
                            <el-dropdown-item v-for="demo in demos" :key="demo.id" :command="demo">
                                {{ demo.name }}
                            </el-dropdown-item>
                        </el-dropdown-menu>
                    </template>
                 </el-dropdown>
                 <el-button type="danger" @click="stopTask" :disabled="!isRunning">Stop Running</el-button>
                 <el-button type="primary" @click="saveParams">Save Params</el-button>
              </div>
            </div>
          </template>
          <ParamGroupsEditor
            :groups="matlabParamGroups"
            :params="params"
            v-model:active-names="activeNames"
            v-model:params-json="paramsJson"
            show-global
            show-advanced
            @sync-json="syncJsonToObj"
          />
        </el-card>

        <el-card class="section-card" v-loading="loading">
          <template #header>
            <div class="card-header">
              <span>独立 Video 生成参数</span>
              <div class="actions">
                <el-button type="primary" @click="saveParams">Save Video Params</el-button>
                <el-button type="success" @click="runVideo" :disabled="isRunning">生成视频</el-button>
              </div>
            </div>
          </template>
          <ParamGroupsEditor
            :groups="videoParamGroups"
            :params="params"
            v-model:active-names="videoActiveNames"
          />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="预览" name="preview">
        <Nd2PreviewPanel
          v-model:series="nd2Series"
          v-model:z="nd2Z"
          v-model:c="nd2C"
          v-model:c2="nd2C2"
          v-model:t="nd2T"
          v-model:lut="nd2Lut"
          v-model:lut2="nd2Lut2"
          v-model:preview-mode="nd2PreviewMode"
          :loading="nd2PreviewLoading"
          :error="nd2PreviewError"
          :series-options="nd2SeriesOptions"
          :quality="nd2PreviewQuality"
          :max-z="nd2MaxZ"
          :max-t="nd2MaxT"
          :channel-options="nd2ChannelOptions"
          :preview-url="nd2PreviewUrl"
          :format-series-label="formatNd2SeriesLabel"
          @refresh-fast="loadNd2FastPreview"
          @load-full="loadNd2FullPreview"
          @control-change="onNd2PreviewControlChange"
          @series-change="onNd2SeriesChange"
        />

        <VideoPreviewPanel
          v-model:selected-video-channel="selectedVideoChannel"
          :visible="currentRunStatus === 'SUCCEEDED' && (currentRunMode === 'debug' || currentRunMode === 'video')"
          :loading="artifactsLoading"
          :current-run-mode="currentRunMode"
          :video-artifacts="videoArtifacts"
          :has-merge-video="hasMergeVideo"
          :current-video-url="currentVideoUrl"
          :current-video-mime="currentVideoMime"
          :current-video-name="currentVideoName"
          :download-only-videos="downloadOnlyVideos"
          :artifact-load-errors="artifactLoadErrors"
          @refresh="fetchArtifacts"
          @retry="retryFetchArtifacts"
          @video-error="handleVideoError"
          @download-artifact="downloadArtifact"
        />
      </el-tab-pane>
    </el-tabs>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import http from '@/api/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { paramGroups } from '@/config/taskParamsSchema'
import defaultParams from '@/config/defaultParams.json'
import RunHistoryPanel from '@/components/task-detail/RunHistoryPanel.vue'
import ExecutionPanel from '@/components/task-detail/ExecutionPanel.vue'
import RunStatusResultsPanel from '@/components/task-detail/RunStatusResultsPanel.vue'
import ParamGroupsEditor from '@/components/task-detail/ParamGroupsEditor.vue'
import RuntimeLogPanel from '@/components/task-detail/RuntimeLogPanel.vue'
import Nd2PreviewPanel from '@/components/task-detail/Nd2PreviewPanel.vue'
import VideoPreviewPanel from '@/components/task-detail/VideoPreviewPanel.vue'

const createDefaultParams = () => {
    // Deep copy the JSON template
    return JSON.parse(JSON.stringify(defaultParams))
}

const route = useRoute()
const router = useRouter()
const taskId = route.params.id as string
const nd2Filename = ref('')
const loading = ref(false)
const params = ref<any>(createDefaultParams())
const paramsJson = ref(JSON.stringify(params.value, null, 2))
const taskStatus = ref('UNKNOWN')
const history = ref<any[]>([])
const selectedRuns = ref<any[]>([])
const currentRunId = ref<string | null>(null)
const logs = ref('')
const lastLogChangeAt = ref<number>(Date.now())
const stallWarning = ref('')
let logInterval: any = null
let transferInterval: any = null
const transfer = ref<any>(null)
const transferLastUpdatedAt = ref<number>(0)

const activeDetailTab = ref('overview')
const activeNames = ref(['Read']) // Optimized: Only open first group by default
const videoActiveNames = ref(['Video'])
const matlabParamGroups = computed(() => paramGroups.filter(group => group.key !== 'Video'))
const videoParamGroups = computed(() => paramGroups.filter(group => group.key === 'Video'))
const artifactsLoading = ref(false)
type VideoArtifact = {
    path: string
    name: string
    label?: string
    mime?: string
    playable?: boolean
    channel?: string | null
    mode?: string | null
}

const videoArtifacts = ref<VideoArtifact[]>([])
const selectedVideoChannel = ref<'C01' | 'C02' | 'MERGE'>('C01')

const artifactLoadErrors = ref<string[]>([])
const videoObjectUrl = ref<string>('')
const videoLoadSeq = ref(0)
const videoRetryCount = ref(0)
let videoRetryTimer: any = null
const nd2Metadata = ref<any>(null)
const nd2PreviewLoading = ref(false)
const nd2PreviewError = ref('')
const nd2PreviewUrl = ref('')
const nd2Series = ref(0)
const nd2Z = ref(0)
const nd2C = ref(0)
const nd2C2 = ref(1)
const nd2T = ref(0)
const nd2Lut = ref('gray')
const nd2Lut2 = ref('red')
const nd2PreviewMode = ref<'single' | 'merge'>('single')
const nd2PreviewQuality = ref<'fast' | 'full'>('fast')
const nd2PreviewMaxPx = ref(512)

const currentRunMode = computed(() => {
    if (currentRunId.value) {
        const run = history.value.find((r: any) => r.id === currentRunId.value)
        if (run) return run.run_mode
    }
    // Fallback based on params if not linked to a specific run in history yet (e.g. just starting)
    // But be careful, params might change. Best to rely on history.
    return 'unknown'
})

const currentVideo = computed(() => {
    const playable = videoArtifacts.value.filter(v => v.playable !== false)
    if (!playable.length) return null
    if (selectedVideoChannel.value === 'MERGE') {
        return playable.find(v => v.mode === 'merge' || /merge/i.test(v.name)) ?? playable[0]
    }
    if (selectedVideoChannel.value === 'C01') {
        return playable.find(v => v.channel === 'C01' || /refC01|C01/i.test(v.name)) ?? playable[0]
    }
    return playable.find(v => v.channel === 'C02' || /othC02|C02/i.test(v.name)) ?? playable[0]
})

const currentVideoUrl = computed(() => videoObjectUrl.value)

const currentVideoName = computed(() => currentVideo.value?.name ?? '')
const currentVideoMime = computed(() => currentVideo.value?.mime || 'video/mp4')
const downloadOnlyVideos = computed(() => videoArtifacts.value.filter(v => v.playable === false))
const hasMergeVideo = computed(() => videoArtifacts.value.some(v => v.mode === 'merge' || /merge/i.test(v.name)))
const nd2SeriesOptions = computed(() => Array.isArray(nd2Metadata.value?.series) ? nd2Metadata.value.series : [])
const nd2CurrentSeries = computed(() => nd2SeriesOptions.value.find((s: any) => s.index === nd2Series.value) || nd2SeriesOptions.value[0])
const nd2MaxZ = computed(() => Math.max(0, Number(nd2CurrentSeries.value?.size_z || 1) - 1))
const nd2MaxT = computed(() => Math.max(0, Number(nd2CurrentSeries.value?.size_t || 1) - 1))
const nd2ChannelOptions = computed(() => {
    const channels = Array.isArray(nd2CurrentSeries.value?.channels) ? nd2CurrentSeries.value.channels : []
    if (channels.length) {
        return channels.map((ch: any, idx: number) => {
            const oneBased = Number(ch.index || idx + 1)
            const name = ch.name || `C${String(oneBased).padStart(2, '0')}`
            return { value: Math.max(0, oneBased - 1), label: `C${String(oneBased).padStart(2, '0')} ${name}` }
        })
    }
    const n = Math.max(1, Number(nd2CurrentSeries.value?.size_c || 1))
    return Array.from({ length: n }, (_, idx) => ({ value: idx, label: `C${String(idx + 1).padStart(2, '0')}` }))
})

const formatNd2SeriesLabel = (s: any) => {
    const idx = Number(s?.index ?? 0)
    const xy = `XY${String(idx + 1).padStart(3, '0')}`
    const name = s?.name && !String(s.name).startsWith('Series ') ? ` · ${s.name}` : ''
    const size = s?.size_x && s?.size_y ? ` · ${s.size_x}x${s.size_y}` : ''
    return `${xy}${name}${size}`
}

const normalizeNd2PreviewControls = () => {
    nd2Z.value = Math.min(Math.max(0, nd2Z.value || 0), nd2MaxZ.value)
    nd2T.value = Math.min(Math.max(0, nd2T.value || 0), nd2MaxT.value)
    const values = nd2ChannelOptions.value.map((ch: any) => ch.value)
    if (!values.includes(nd2C.value)) nd2C.value = values[0] ?? 0
    if (!values.includes(nd2C2.value)) nd2C2.value = values.find((v: number) => v !== nd2C.value) ?? values[0] ?? 0
    if (nd2PreviewMode.value === 'merge' && values.length < 2) {
        nd2PreviewMode.value = 'single'
    }
}

const loadNd2Metadata = async () => {
    try {
        const res = await http.get(`/tasks/${taskId}/nd2/metadata`, { timeout: 180000 })
        nd2Metadata.value = res.data
        const first = nd2SeriesOptions.value[0]
        if (first) {
            nd2Series.value = first.index
            nd2Z.value = 0
            nd2C.value = 0
            nd2C2.value = Math.max(0, Math.min(1, Number(first.size_c || 1) - 1))
            nd2T.value = 0
            nd2PreviewQuality.value = 'fast'
        }
        normalizeNd2PreviewControls()
        nd2PreviewError.value = ''
        await loadNd2Preview()
    } catch (e: any) {
        nd2PreviewError.value = e?.response?.data?.detail || e?.message || 'ND2 preview is not available'
    }
}

const loadNd2Preview = async () => {
    nd2PreviewLoading.value = true
    try {
        const res = await http.get(`/tasks/${taskId}/nd2/preview`, {
            params: {
                series: nd2Series.value,
                z: nd2Z.value,
                c: nd2C.value,
                c2: nd2C2.value,
                t: nd2T.value,
                mode: nd2PreviewMode.value,
                lut: nd2Lut.value,
                lut2: nd2Lut2.value,
                quality: nd2PreviewQuality.value,
                max_px: nd2PreviewMaxPx.value,
            },
            responseType: 'blob',
            timeout: 180000,
        })
        if (nd2PreviewUrl.value) {
            try {
                URL.revokeObjectURL(nd2PreviewUrl.value)
            } catch (e) {
            }
        }
        nd2PreviewUrl.value = URL.createObjectURL(res.data)
        nd2PreviewError.value = ''
    } catch (e: any) {
        nd2PreviewError.value = e?.response?.data?.detail || e?.message || 'Failed to load ND2 preview'
    } finally {
        nd2PreviewLoading.value = false
    }
}

const loadNd2FastPreview = () => {
    nd2PreviewQuality.value = 'fast'
    loadNd2Preview()
}

const loadNd2FullPreview = () => {
    nd2PreviewQuality.value = 'full'
    loadNd2Preview()
}

const onNd2PreviewControlChange = () => {
    normalizeNd2PreviewControls()
    loadNd2FastPreview()
}

const onNd2SeriesChange = () => {
    nd2Z.value = 0
    nd2T.value = 0
    nd2C.value = 0
    nd2C2.value = nd2ChannelOptions.value.length > 1 ? nd2ChannelOptions.value[1].value : 0
    normalizeNd2PreviewControls()
    loadNd2FastPreview()
}

watch([() => currentVideo.value?.path, currentRunId], async () => {
    videoRetryCount.value = 0
    await loadCurrentVideo()
})

// Computed
const isRunning = computed(() => {
    const run = currentRunStatus.value
    const task = taskStatus.value
    const values = [run, task].filter(v => typeof v === 'string') as string[]
    return values.some(v => v === 'RUNNING' || v === 'PENDING' || v === 'QUEUED' || v.startsWith('RUNNING'))
})
const currentRunStatus = computed(() => {
    if (currentRunId.value) {
        const run = history.value.find((r: any) => r.id === currentRunId.value)
        if (run) return run.status
    }
    return taskStatus.value
})
const queuePosition = ref<{ status: string; position: number; total_queued: number } | null>(null)
const isCurrentRunSelected = computed(() => !!currentRunId.value)
const displayedLogs = computed(() => {
    if (stallWarning.value) return `${stallWarning.value}\n\n${logs.value || ''}`.trim()
    return logs.value
})

const transferState = computed(() => String(transfer.value?.state ?? 'unknown'))
const transferPercent = computed(() => {
    const v = transfer.value?.percent
    if (typeof v !== 'number') return null
    if (!isFinite(v)) return null
    return Math.max(0, Math.min(100, Math.round(v)))
})
const transferVisible = computed(() => {
    if (!currentRunId.value && !isRunning.value) return false
    const state = transferState.value
    const partMinio = Array.isArray(transfer.value?.part_minio_files) ? transfer.value.part_minio_files.length : 0
    const part = Array.isArray(transfer.value?.part_files) ? transfer.value.part_files.length : 0
    if (state && state !== 'unknown') return true
    if (partMinio > 0 || part > 0) return true
    return !!currentRunId.value
})
const transferTagType = computed(() => {
    const state = transferState.value
    if (state === 'ready') return 'success'
    if (state === 'failed') return 'danger'
    if (state === 'canceled') return 'warning'
    if (state === 'transferring') return 'primary'
    return 'info'
})
const transferLabel = computed(() => {
    const state = transferState.value
    if (state === 'ready') return '已就绪'
    if (state === 'failed') return '传输失败'
    if (state === 'canceled') return '已取消'
    if (state === 'transferring') return '文件传输中'
    return '状态未知'
})
const transferProgressStatus = computed(() => {
    const state = transferState.value
    if (state === 'failed') return 'exception'
    if (state === 'canceled') return 'warning'
    if (state === 'ready') return 'success'
    return undefined
})
const formatBytes = (value: any) => {
    const n = typeof value === 'number' ? value : Number(value)
    if (!isFinite(n) || n <= 0) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    let idx = 0
    let v = n
    while (v >= 1024 && idx < units.length - 1) {
        v /= 1024
        idx += 1
    }
    return `${v.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`
}
const formatDuration = (value: any) => {
    const s = typeof value === 'number' ? value : Number(value)
    if (!isFinite(s) || s === null) return ''
    const sec = Math.max(0, Math.floor(s))
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    const ss = sec % 60
    if (h > 0) return `${h}h ${m}m ${ss}s`
    if (m > 0) return `${m}m ${ss}s`
    return `${ss}s`
}
const transferDetailText = computed(() => {
    const t = transfer.value || {}
    const msg = typeof t.message === 'string' ? t.message : ''
    const done = t.bytes_done
    const total = t.bytes_total
    const eta = t.eta_seconds
    const speed = t.speed_bps
    const partsMinio = Array.isArray(t.part_minio_files) ? t.part_minio_files.length : 0
    const parts = Array.isArray(t.part_files) ? t.part_files.length : 0
    const bits: string[] = []
    if (typeof done === 'number' || typeof total === 'number') {
        bits.push(`${formatBytes(done)} / ${formatBytes(total)}`)
    }
    if (typeof speed === 'number' && isFinite(speed) && speed > 0) {
        bits.push(`${formatBytes(speed)}/s`)
    }
    if (typeof eta === 'number' && isFinite(eta)) {
        bits.push(`ETA ${formatDuration(eta)}`)
    }
    if (partsMinio > 0) {
        bits.push(`${partsMinio} 个.part.minio`)
    }
    if (parts > 0) {
        bits.push(`${parts} 个.part`)
    }
    if (msg) bits.push(msg)
    return bits.join(' · ')
})
const coldArchiveDetailText = computed(() => {
    const cold = transfer.value?.cold_archive
    if (!cold) return ''
    const state = String(cold.state || 'unknown')
    const done = cold.bytes_done
    const total = cold.bytes_total
    const msg = typeof cold.message === 'string' ? cold.message : ''
    const bits: string[] = []
    if (state === 'completed' && cold.verified) bits.push('已完成并校验')
    else if (state === 'copying') bits.push('后台复制中')
    else if (state === 'queued') bits.push('等待复制')
    else if (state === 'failed') bits.push('失败，热盘文件会保留')
    else bits.push(state)
    if (typeof done === 'number' || typeof total === 'number') {
        bits.push(`${formatBytes(done)} / ${formatBytes(total)}`)
    }
    if (msg) bits.push(msg)
    return bits.join(' · ')
})

const handleVideoError = () => {
    artifactLoadErrors.value.push('Video playback failed (network or file missing).')
    if (videoRetryCount.value >= 3) return
    videoRetryCount.value += 1
    if (videoRetryTimer) clearTimeout(videoRetryTimer)
    videoRetryTimer = setTimeout(() => {
        loadCurrentVideo()
    }, 800 * videoRetryCount.value)
}

const loadCurrentVideo = async () => {
    const v = currentVideo.value
    if (!v) {
        if (videoObjectUrl.value) {
            try {
                URL.revokeObjectURL(videoObjectUrl.value)
            } catch (e) {
            }
        }
        videoObjectUrl.value = ''
        return
    }
    const seq = Date.now()
    videoLoadSeq.value = seq
    try {
        const params: any = { path: v.path }
        if (currentRunId.value) params.run_id = currentRunId.value
        const res = await http.get(`/tasks/${taskId}/artifacts/file`, { params, responseType: 'blob' })
        if (videoLoadSeq.value !== seq) return
        if (videoObjectUrl.value) {
            try {
                URL.revokeObjectURL(videoObjectUrl.value)
            } catch (e) {
            }
        }
        videoObjectUrl.value = URL.createObjectURL(res.data)
    } catch (e: any) {
        artifactLoadErrors.value.push(e?.response?.data?.detail || e?.message || 'Failed to load video')
    }
}

const fetchArtifacts = async () => {
    artifactsLoading.value = true
    artifactLoadErrors.value = []
    try {
        const params: any = {}
        if (currentRunId.value) params.run_id = currentRunId.value
        const res = await http.get(`/tasks/${taskId}/artifacts/list`, { params })
        videoArtifacts.value = Array.isArray(res.data?.videos) ? res.data.videos : []

        if (hasMergeVideo.value && currentRunMode.value === 'video') {
            selectedVideoChannel.value = 'MERGE'
        } else if (videoArtifacts.value.length && selectedVideoChannel.value === 'C02') {
            selectedVideoChannel.value = 'C01'
        }
        videoRetryCount.value = 0
        await loadCurrentVideo()
    } catch (e: any) {
        artifactLoadErrors.value.push(e?.response?.data?.detail || e?.message || 'Failed to load artifacts')
    } finally {
        artifactsLoading.value = false
    }
}

const retryFetchArtifacts = async () => {
    await fetchArtifacts()
}

const resetToDefaults = async () => {
    try {
        await ElMessageBox.confirm('Are you sure to reset all parameters to defaults?', 'Warning', {
            confirmButtonText: 'Reset',
            cancelButtonText: 'Cancel',
            type: 'warning',
        })
        
        params.value = createDefaultParams()
        ElMessage.success('Reset to defaults')
    } catch (e) {
        // Cancelled
    }
}

// --- Demo Params Logic ---
const demos = ref<any[]>([])

const fetchDemos = async () => {
    try {
        const res = await http.get('/tasks/params/demos')
        demos.value = res.data || []
    } catch (e) {
        console.error('Failed to fetch demos', e)
    }
}

const deepMerge = (target: any, source: any) => {
    for (const key of Object.keys(source)) {
        if (source[key] instanceof Object && key in target && target[key] instanceof Object && !Array.isArray(source[key])) {
            deepMerge(target[key], source[key])
        } else {
            target[key] = source[key]
        }
    }
    return target
}

const applyDemo = async (demo: any) => {
    try {
        await ElMessageBox.confirm(
            `Apply demo preset "${demo.name}"? \nThis will overwrite current parameters. (Not saved automatically)`, 
            'Confirm', 
            {
                confirmButtonText: 'Apply',
                cancelButtonText: 'Cancel',
                type: 'warning',
            }
        )
        
        const res = await http.get(`/tasks/params/demos/${demo.id}`)
        const demoParams = res.data
        
        // Merge: Default + Demo
        const base = createDefaultParams()
        const merged = deepMerge(base, demoParams)
        
        params.value = merged
        ElMessage.success(`Applied demo: ${demo.name}`)
    } catch (e: any) {
        if (e !== 'cancel') {
             ElMessage.error(e?.response?.data?.detail || 'Failed to apply demo')
        }
    }
}

const handlePresetCommand = (cmd: any) => {
    if (cmd === 'default') {
        resetToDefaults()
    } else {
        applyDemo(cmd)
    }
}

// Sync Object -> JSON (when object changes via form)
watch(params, (newVal) => {
    paramsJson.value = JSON.stringify(newVal, null, 2)
}, { deep: true })

// Sync JSON -> Object (when JSON text changes manually)
const syncJsonToObj = () => {
    try {
        params.value = JSON.parse(paramsJson.value)
    } catch (e) {
        // Ignore syntax errors while typing
    }
}

const fetchHistory = async () => {
    try {
        const res = await http.get(`/tasks/${taskId}/history`)
        // Handle pagination response { items: [], total: number }
        if (res.data && Array.isArray(res.data.items)) {
            history.value = res.data.items
        } else if (Array.isArray(res.data)) {
            // Fallback for old format
            history.value = res.data
        } else {
            history.value = []
        }
        
        if (currentRunId.value) {
            const run = history.value.find((r: any) => r.id === currentRunId.value)
            if (run && run.status !== taskStatus.value && !isRunning.value) {
                // Keep sync
            }
        }

        // Auto fetch artifacts if run succeeded and debug mode
        // Use nextTick to ensure computed properties are updated? 
        // Or just rely on data.
        const currentRun = history.value.find((r: any) => r.id === currentRunId.value)
        // const isDebug = currentRun?.run_mode === 'debug' || params.value.Debug?.Enable
        
        if (currentRun?.status === 'SUCCEEDED' && !videoArtifacts.value.length) {
            fetchArtifacts()
        }
    } catch (e) {
        console.error(e)
    }
}

const handleSelectionChange = (val: any[]) => {
    selectedRuns.value = val
}

const viewRun = (run: any) => {
    currentRunId.value = run.id
    logs.value = '' 
    // Reset artifacts
    videoArtifacts.value = []
    artifactLoadErrors.value = []
    
    fetchLogs()
    // Fetch artifacts if SUCCEEDED
    if (run.status === 'SUCCEEDED' || run.status.includes('DEBUG')) { // Allow DEBUG_SUCCEEDED etc
         fetchArtifacts()
    }
    
    nextTick(() => {
        const logCard = document.querySelector('.el-card__header .el-icon-monitor')?.closest('.el-card')
        if (logCard) {
            logCard.scrollIntoView({ behavior: 'smooth' })
        }
    })
}

const deleteRun = async (runId: string) => {
    try {
        await ElMessageBox.confirm('Are you sure to delete this run? This cannot be undone.', 'Warning', {
            confirmButtonText: 'Delete',
            cancelButtonText: 'Cancel',
            type: 'warning',
        })
        await http.delete(`/tasks/${taskId}/history/${runId}`)
        ElMessage.success('Run deleted')
        fetchHistory()
    } catch (e) {
        // Cancelled
    }
}

const deleteSelectedRuns = async () => {
     try {
        await ElMessageBox.confirm(`Are you sure to delete ${selectedRuns.value.length} runs?`, 'Warning', {
            confirmButtonText: 'Delete',
            cancelButtonText: 'Cancel',
            type: 'warning',
        })
        const ids = selectedRuns.value.map(r => r.id)
        await http.post(`/tasks/${taskId}/history/delete`, { run_ids: ids })
        ElMessage.success('Runs deleted')
        fetchHistory()
    } catch (e) {
        // Cancelled
    }
}

const fetchParams = async () => {
    loading.value = true
    try {
        console.log('Fetching task info...')
        // Get Task Info
        const taskRes = await http.get(`/tasks/${taskId}`)
        taskStatus.value = taskRes.data.status
        currentRunId.value = taskRes.data.run_id_current
        if (taskRes.data.nd2_object_key) {
             const parts = taskRes.data.nd2_object_key.split('/')
             nd2Filename.value = parts[parts.length - 1]
        }
        
        console.log('Fetching params...')
        // Get Params
        const paramRes = await http.get(`/tasks/${taskId}/params`)
        console.log('Params received:', paramRes.data)
        if (paramRes.data) {
            params.value = paramRes.data
            paramsJson.value = JSON.stringify(params.value, null, 2)
        }
    } catch (e) {
        console.error('Error fetching params:', e)
        ElMessage.error('Failed to load task info')
    } finally {
        loading.value = false
        console.log('Loading set to false')
    }
}

const saveParams = async () => {
    try {
        const parsed = JSON.parse(paramsJson.value)
        await http.put(`/tasks/${taskId}/params`, parsed) 
        ElMessage.success('Parameters saved')
    } catch (e: any) {
        console.error(e)
        if (e instanceof SyntaxError) {
             ElMessage.error('Invalid JSON format')
        } else {
             ElMessage.error('Failed to save params: ' + (e.message || 'Unknown error'))
        }
    }
}

const runDebug = async () => {
    params.value.Debug.Enable = true
    await saveParams()
    try {
        const res = await http.post(`/tasks/${taskId}/debug/run`)
        currentRunId.value = res.data.run_id
        logs.value = ''
        startLogPolling()
        ElMessage.success('已进入队列，等待启动')
        fetchParams()
        fetchHistory()
    } catch (e: any) {
        console.error(e)
        ElMessage.error('Failed to start debug: ' + (e.response?.data?.detail || e.message))
    }
}

const runFinal = async () => {
    params.value.Debug.Enable = false
    await saveParams()
    try {
        const res = await http.post(`/tasks/${taskId}/final/run`)
        currentRunId.value = res.data.run_id
        logs.value = ''
        startLogPolling()
        ElMessage.success('已进入队列，等待启动')
        fetchParams()
        fetchHistory()
    } catch (e: any) {
        console.error(e)
        ElMessage.error('Failed to start analysis: ' + (e.response?.data?.detail || e.message))
    }
}

const runVideo = async () => {
    await saveParams()
    try {
        const res = await http.post(`/tasks/${taskId}/video/run`)
        currentRunId.value = res.data.run_id
        logs.value = ''
        videoArtifacts.value = []
        startLogPolling()
        ElMessage.success('视频任务已进入队列')
        fetchParams()
        fetchHistory()
    } catch (e: any) {
        console.error(e)
        ElMessage.error('Failed to start video generation: ' + (e.response?.data?.detail || e.message))
    }
}

const stopTask = async () => {
    try {
        await http.post(`/tasks/${taskId}/stop`)
        ElMessage.success('Stop signal sent')
        fetchParams()
        fetchHistory()
    } catch (e: any) {
        if (e?.response?.status === 404) {
            ElMessage.error('任务不存在或后端未加载停止接口')
            stopLogPolling()
            stopTransferPolling()
            router.push('/tasks')
            return
        }
        ElMessage.error('Failed to stop: ' + e.message)
    }
}

const fetchTransferStatus = async () => {
    try {
        const params: any = {}
        if (currentRunId.value) params.run_id = currentRunId.value
        const res = await http.get(`/tasks/${taskId}/transfer/status`, { params })
        transfer.value = res.data
        transferLastUpdatedAt.value = Date.now()
    } catch (e: any) {
        const status = e?.response?.status
        if (status === 404) {
            transfer.value = { state: 'deleted', message: '任务或接口不存在（可能后端未重启或任务已删除）' }
            stopTransferPolling()
        }
    }
}

const startTransferPolling = () => {
    if (transferInterval) clearInterval(transferInterval)
    fetchTransferStatus()
    transferInterval = setInterval(fetchTransferStatus, 1000)
}

const stopTransferPolling = () => {
    if (transferInterval) clearInterval(transferInterval)
    transferInterval = null
}

const filenameFromDisposition = (disposition: any, fallback: string) => {
    const value = typeof disposition === 'string' ? disposition : ''
    const match = value.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i)
    if (!match) return fallback
    try {
        return decodeURIComponent(match[1].replace(/"/g, ''))
    } catch {
        return match[1].replace(/"/g, '')
    }
}

const downloadPreview = () => {
    const params: any = {}
    if (currentRunId.value) params.run_id = currentRunId.value
    http
        .get(`/tasks/${taskId}/preview/download`, { params, responseType: 'blob' })
        .then((res) => {
            const blobUrl = URL.createObjectURL(res.data)
            const a = document.createElement('a')
            a.href = blobUrl
            a.download = 'preview.mp4'
            document.body.appendChild(a)
            a.click()
            a.remove()
            setTimeout(() => URL.revokeObjectURL(blobUrl), 2000)
        })
        .catch((e: any) => {
            ElMessage.error(e?.response?.data?.detail || e?.message || 'Download failed')
        })
}

const downloadAllResults = () => {
    const params: any = {}
    if (currentRunId.value) params.run_id = currentRunId.value
    http
        .get(`/tasks/${taskId}/artifacts/archive`, { params, responseType: 'blob' })
        .then((res) => {
            const blobUrl = URL.createObjectURL(res.data)
            const a = document.createElement('a')
            a.href = blobUrl
            a.download = filenameFromDisposition(res.headers?.['content-disposition'], 'results.zip')
            document.body.appendChild(a)
            a.click()
            a.remove()
            setTimeout(() => URL.revokeObjectURL(blobUrl), 2000)
        })
        .catch((e: any) => {
            ElMessage.error(e?.response?.data?.detail || e?.message || 'Download failed')
        })
}

const downloadResult = () => {
    const params: any = {}
    if (currentRunId.value) params.run_id = currentRunId.value
    http
        .get(`/tasks/${taskId}/results/download`, { params, responseType: 'blob' })
        .then((res) => {
            const blobUrl = URL.createObjectURL(res.data)
            const a = document.createElement('a')
            a.href = blobUrl
            a.download = 'result.csv'
            document.body.appendChild(a)
            a.click()
            a.remove()
            setTimeout(() => URL.revokeObjectURL(blobUrl), 2000)
        })
        .catch((e: any) => {
            ElMessage.error(e?.response?.data?.detail || e?.message || 'Download failed')
        })
}

const downloadArtifact = (path: string) => {
    const params: any = { path, download: true }
    if (currentRunId.value) params.run_id = currentRunId.value
    http
        .get(`/tasks/${taskId}/artifacts/file`, { params, responseType: 'blob' })
        .then((res) => {
            const blobUrl = URL.createObjectURL(res.data)
            const a = document.createElement('a')
            a.href = blobUrl
            a.download = path.split('/').pop() || 'download'
            document.body.appendChild(a)
            a.click()
            a.remove()
            setTimeout(() => URL.revokeObjectURL(blobUrl), 2000)
        })
        .catch((e: any) => {
            ElMessage.error(e?.response?.data?.detail || e?.message || 'Download failed')
        })
}

// Logging Logic
const fetchLogs = async () => {
    if (!currentRunId.value) return
    try {
        const res = await http.get(`/tasks/${taskId}/history/${currentRunId.value}/log`)
        const content = String(res.data?.content ?? '')
        const exists = res.data?.exists
        const runStatus = res.data?.run_status
        const taskStatus = res.data?.task_status
        const effective = content || (
            exists === false
                ? 'Waiting for worker to create runtime.log...'
                : (runStatus === 'RUNNING' || String(taskStatus ?? '').startsWith('RUNNING'))
                    ? 'Waiting for runtime output...'
                    : ''
        )
        if (effective !== logs.value) {
            logs.value = effective
            stallWarning.value = ''
            lastLogChangeAt.value = Date.now()
        } else if (isRunning.value) {
            const idleMs = Date.now() - lastLogChangeAt.value
            if (idleMs > 60_000 && !stallWarning.value) {
                stallWarning.value = `WARN: No new output for ${(idleMs / 1000).toFixed(0)}s. Check worker/script status.`
            }
        }
    } catch (e) {
    }
}

const fetchQueuePosition = async () => {
    if (!taskId) return
    try {
        const res = await http.get(`/tasks/${taskId}/queue-position`)
        queuePosition.value = res.data
    } catch (e) {
        console.error("Failed to fetch queue position", e)
    }
}

const pollStatus = () => {
    fetchHistory()
    if (currentRunStatus.value === 'RUNNING' || currentRunStatus.value === 'QUEUED') {
        fetchLogs()
        if (currentRunStatus.value === 'QUEUED') {
            fetchQueuePosition()
        }
    }
    // Check if artifacts need fetching
    if (currentRunStatus.value === 'SUCCEEDED' && ['debug', 'final', 'video'].includes(currentRunMode.value) && !videoArtifacts.value.length) {
         fetchArtifacts()
    }
}

const startLogPolling = () => {
    if (logInterval) clearInterval(logInterval)
    pollStatus()
    logInterval = setInterval(pollStatus, 2000)
}

const stopLogPolling = () => {
    if (logInterval) clearInterval(logInterval)
    logInterval = null
}

watch(isRunning, (val) => {
    if (val) {
        startLogPolling()
        startTransferPolling()
    } else {
        stopLogPolling()
        stopTransferPolling()
        fetchLogs() 
        fetchHistory()
    }
})

watch(currentRunId, (val) => {
    if (val) {
        if (isRunning.value) {
             startLogPolling()
             startTransferPolling()
        } else {
            stopLogPolling()
            startTransferPolling()
            fetchLogs()
        }
    } else {
        stopTransferPolling()
    }
})

onMounted(() => {
    fetchParams()
    fetchHistory()
    fetchTransferStatus()
    fetchDemos()
    loadNd2Metadata()
})

onUnmounted(() => {
    stopLogPolling()
    stopTransferPolling()
    if (videoRetryTimer) clearTimeout(videoRetryTimer)
    videoRetryTimer = null
    if (videoObjectUrl.value) {
        try {
            URL.revokeObjectURL(videoObjectUrl.value)
        } catch (e) {
        }
    }
    videoObjectUrl.value = ''
    if (nd2PreviewUrl.value) {
        try {
            URL.revokeObjectURL(nd2PreviewUrl.value)
        } catch (e) {
        }
    }
    nd2PreviewUrl.value = ''
})
</script>

<style scoped>
.task-params {
    padding: 20px;
}
.header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 20px;
}
.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.actions {
    display: flex;
    gap: 10px;
    align-items: center;
}

.detail-tabs {
    background: #fff;
    padding: 0 18px 18px;
    border-radius: 6px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.section-card {
    margin-top: 18px;
}

.terminal-card {
    margin-top: 20px;
    background-color: #1e1e1e;
    color: #e0e0e0;
}

.terminal-output {
    height: 300px;
    overflow-y: auto;
    font-family: Consolas, Monaco, monospace;
    white-space: pre-wrap;
    font-size: 12px;
    line-height: 1.4;
}
</style>
