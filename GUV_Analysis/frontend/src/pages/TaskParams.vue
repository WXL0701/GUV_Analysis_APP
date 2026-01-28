<template>
  <div class="task-params">
    <div class="header">
      <div style="display: flex; flex-direction: column; gap: 5px;">
          <h2>Task Configuration: {{ taskId }}</h2>
          <el-tag v-if="nd2Filename" type="info" size="small">File: {{ nd2Filename }}</el-tag>
      </div>
      <el-button @click="$router.push('/tasks')">Back to List</el-button>
    </div>

    <!-- Run History -->
    <el-card style="margin-bottom: 20px;">
        <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>Run History</span>
                <el-button type="danger" size="small" :disabled="selectedRuns.length === 0" @click="deleteSelectedRuns">Delete Selected</el-button>
            </div>
        </template>
        <el-table 
            :data="history" 
            @selection-change="handleSelectionChange" 
            style="width: 100%" 
            stripe
            highlight-current-row
        >
            <el-table-column type="selection" width="55" />
            <el-table-column prop="created_at" label="Date" width="180" sortable>
                <template #default="scope">
                    {{ new Date(scope.row.created_at).toLocaleString() }}
                </template>
            </el-table-column>
            <el-table-column 
                prop="run_mode" 
                label="Mode" 
                width="100"
                :filters="[{ text: 'Debug', value: 'debug' }, { text: 'Final', value: 'final' }]"
                :filter-method="(value: any, row: any) => row.run_mode === value"
            >
                <template #default="scope">
                    <el-tag :type="scope.row.run_mode === 'debug' ? 'warning' : 'success'">{{ scope.row.run_mode }}</el-tag>
                </template>
            </el-table-column>
            <el-table-column prop="params_snapshot" label="Params" min-width="200">
                <template #default="scope">
                    <div v-if="scope.row.params_snapshot" style="display: flex; gap: 5px; flex-wrap: wrap;">
                        <el-tag size="small" type="info" v-if="scope.row.params_snapshot.PixelSize_um">Px: {{ scope.row.params_snapshot.PixelSize_um }}</el-tag>
                        <el-tag size="small" type="info" v-if="scope.row.params_snapshot.FrameInterval_s">Int: {{ scope.row.params_snapshot.FrameInterval_s }}s</el-tag>
                        <el-tag size="small" type="warning" v-if="scope.row.params_snapshot.Debug?.Enable">Debug</el-tag>
                    </div>
                </template>
            </el-table-column>
            <el-table-column 
                prop="status" 
                label="Status" 
                width="120"
                :filters="[{ text: 'RUNNING', value: 'RUNNING' }, { text: 'SUCCEEDED', value: 'SUCCEEDED' }, { text: 'FAILED', value: 'FAILED' }]"
                :filter-method="(value: any, row: any) => row.status === value"
            >
                <template #default="scope">
                     <el-tag :type="scope.row.status === 'RUNNING' ? 'primary' : scope.row.status === 'FAILED' ? 'danger' : 'success'">{{ scope.row.status }}</el-tag>
                </template>
            </el-table-column>
             <el-table-column prop="id" label="Run ID" width="280">
                 <template #default="scope">
                    <el-link type="primary" @click="viewRun(scope.row)">{{ scope.row.id }}</el-link>
                 </template>
            </el-table-column>
            <el-table-column label="Actions">
                <template #default="scope">
                    <el-button size="small" type="primary" @click="viewRun(scope.row)">View</el-button>
                    <el-button size="small" type="danger" @click="deleteRun(scope.row.id)">Delete</el-button>
                </template>
            </el-table-column>
        </el-table>
    </el-card>

    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>Analysis Parameters</span>
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

      <!-- Parameter Form (Structured) -->
      <div class="param-editor">
          <!-- Common Global Settings (Always Visible) -->
           <el-form label-position="top">
                <el-row :gutter="20">
                    <el-col :span="8">
                        <el-form-item label="Pixel Size (um)">
                            <el-input-number v-model="params.PixelSize_um" :step="0.01" />
                        </el-form-item>
                    </el-col>
                    <el-col :span="8">
                        <el-form-item label="Frame Interval (s)">
                            <el-input-number v-model="params.FrameInterval_s" :step="1" />
                        </el-form-item>
                    </el-col>
                </el-row>
           </el-form>

           <el-divider />

           <el-collapse v-model="activeNames">
                <el-collapse-item v-for="group in paramGroups" :key="group.key" :title="group.label" :name="group.key">
                    <el-form label-position="left" label-width="200px">
                        <el-row :gutter="24">
                            <el-col :span="12" v-for="param in group.params" :key="param.key">
                                <el-form-item>
                                    <template #label>
                                        <div style="display: flex; align-items: center; gap: 5px;">
                                            {{ param.label }}
                                            <el-tooltip :content="param.tooltip" placement="top">
                                                <el-icon><QuestionFilled /></el-icon>
                                            </el-tooltip>
                                        </div>
                                    </template>
                                    
                                    <!-- Number -->
                                    <el-input-number 
                                        v-if="param.type === 'number'" 
                                        :model-value="getParamValue(group.key, param.key)"
                                        @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                                        :step="param.step || 1"
                                    />

                                    <!-- Slider -->
                                    <div v-else-if="param.type === 'slider'" style="display: flex; align-items: center; width: 100%;">
                                        <el-slider 
                                            :model-value="getParamValue(group.key, param.key)"
                                            @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                                            :min="param.min" :max="param.max" :step="param.step"
                                            style="flex-grow: 1; margin-right: 15px;"
                                        />
                                        <el-input-number 
                                            :model-value="getParamValue(group.key, param.key)"
                                            @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                                            :step="param.step" size="small" style="width: 100px;"
                                        />
                                    </div>

                                    <!-- Boolean (Switch) -->
                                    <el-switch 
                                        v-else-if="param.type === 'boolean'"
                                        :model-value="getParamValue(group.key, param.key)"
                                        @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                                    />

                                    <!-- Text -->
                                    <el-input 
                                        v-else-if="param.type === 'text'"
                                        :model-value="getParamValue(group.key, param.key)"
                                        @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                                    />

                                    <!-- Select -->
                                    <el-select 
                                        v-else-if="param.type === 'select'"
                                        :model-value="getParamValue(group.key, param.key)"
                                        @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                                    >
                                        <el-option v-for="opt in param.options" :key="opt" :label="opt" :value="opt" />
                                    </el-select>

                                    <!-- Array Number (Text Input for now) -->
                                    <el-input 
                                        v-else-if="param.type === 'array_number'"
                                        :model-value="getInputValue(group.key, param.key)"
                                        @input="(val: string) => onInputValue(group.key, param.key, val)"
                                        @change="(val: string) => onInputBlur(group.key, param.key, val, 'number')"
                                        placeholder="e.g. 1, 2, 5"
                                    />

                                    <!-- Array Select -->
                                     <div v-else-if="param.type === 'array_select'">
                                          <el-input 
                                            :model-value="getInputValue(group.key, param.key)"
                                            @input="(val: string) => onInputValue(group.key, param.key, val)"
                                            @change="(val: string) => onInputBlur(group.key, param.key, val, 'string')"
                                            placeholder="e.g. inner, mem"
                                        />
                                     </div>

                                    <!-- Array String (Tags) -->
                                    <div v-else-if="param.type === 'array_string'">
                                        <el-select
                                            :model-value="getParamValue(group.key, param.key)"
                                            @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                                            multiple
                                            filterable
                                            allow-create
                                            default-first-option
                                            :reserve-keyword="false"
                                            placeholder="Type and press Enter to add..."
                                        >
                                            <el-option
                                                v-for="item in (getParamValue(group.key, param.key) || [])"
                                                :key="item"
                                                :label="item"
                                                :value="item"
                                            />
                                        </el-select>
                                    </div>

                                </el-form-item>
                            </el-col>
                        </el-row>
                    </el-form>
                </el-collapse-item>
                
                 <!-- Advanced JSON -->
                <el-collapse-item title="Advanced Configuration (JSON)" name="advanced">
                    <el-alert title="Edit raw JSON for full control." type="info" :closable="false" style="margin-bottom: 10px;" />
                    <el-input
                        v-model="paramsJson"
                        type="textarea"
                        :rows="15"
                        @change="syncJsonToObj"
                        placeholder="Loading parameters..."
                    />
                </el-collapse-item>
           </el-collapse>
      </div>
      
      <div class="run-controls">
        <el-divider content-position="left">Execution</el-divider>
        <div class="control-row">
            <div v-if="params.Debug?.Enable" style="display: flex; gap: 20px; align-items: center;">
                 <el-alert
                    title="Debug Mode: Runs on a single XY position to generate a preview video."
                    type="info"
                    show-icon
                    :closable="false"
                    style="width: 400px;"
                />
                <el-button type="warning" @click="runDebug" :disabled="isRunning" size="large">
                    <el-icon><VideoPlay /></el-icon> Run Debug (Preview)
                </el-button>
            </div>
            
            <div v-else style="display: flex; gap: 20px; align-items: center;">
                 <el-alert
                    title="Final Mode: Runs full analysis on all positions and generates CSV results."
                    type="success"
                    show-icon
                    :closable="false"
                     style="width: 400px;"
                />
                <el-button type="success" @click="runFinal" :disabled="isRunning" size="large">
                    <el-icon><CaretRight /></el-icon> Run Final Analysis
                </el-button>
            </div>
        </div>
        <el-card v-if="transferVisible" style="margin-top: 12px;">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>ND2 文件传输</span>
              <el-button v-if="transferCanCancel" size="small" type="danger" @click="cancelNd2Transfer">取消传输</el-button>
            </div>
          </template>
          <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
            <el-tag :type="transferTagType">{{ transferLabel }}</el-tag>
            <!-- Detailed Error Log for Failed State -->
            <div v-if="transferState === 'failed'" style="flex: 1; min-width: 300px;">
                 <el-alert :title="transferDetailText" type="error" :closable="false" show-icon style="word-break: break-all;" />
            </div>
            <span v-else style="color: #666; font-size: 12px;">{{ transferDetailText }}</span>
          </div>
          <div v-if="typeof transferPercent === 'number'" style="margin-top: 10px;">
            <el-progress :percentage="transferPercent" :status="transferProgressStatus" />
          </div>
        </el-card>
      </div>

      <!-- Debug Result: Video Preview -->
      <el-card v-if="currentRunStatus === 'SUCCEEDED' && currentRunMode === 'debug'" style="margin-top: 20px;" v-loading="artifactsLoading">
          <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>Debug Video Preview</span>
                <el-button size="small" @click="fetchArtifacts">Refresh</el-button>
              </div>
          </template>
          
            <div v-if="videoArtifacts.length === 0">
                <el-empty description="No debug videos found" />
            </div>
            <div v-else>
                <div style="margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center;">
                    <el-radio-group v-model="selectedVideoChannel">
                        <el-radio-button label="C01">Channel C01 (Ref)</el-radio-button>
                        <el-radio-button label="C02">Channel C02</el-radio-button>
                    </el-radio-group>
                    <el-button @click="toggleFullscreen" :icon="FullScreen" circle title="Toggle Fullscreen" />
                </div>
                
                <div v-if="currentVideoUrl" style="max-width: 800px; margin: 0 auto;">
                    <video 
                        ref="videoPlayer"
                        :key="currentVideoUrl" 
                        controls 
                        style="width: 100%; border-radius: 4px; background: #000;"
                        @error="handleVideoError"
                    >
                        <source :src="currentVideoUrl" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>
                    <div style="margin-top: 10px; text-align: center; color: #666;">
                        Playing: {{ currentVideoName }}
                    </div>
                </div>
                <div v-else>
                        <el-alert title="Video for selected channel not found." type="warning" show-icon :closable="false" />
                </div>
            </div>
          
          <!-- Error Log -->
          <div v-if="artifactLoadErrors.length > 0" style="margin-top: 20px;">
              <el-alert 
                v-for="(err, idx) in artifactLoadErrors" 
                :key="idx"
                :title="err"
                type="error"
                show-icon
                style="margin-bottom: 5px;"
              />
               <el-button type="danger" size="small" @click="retryFetchArtifacts">Retry Connection</el-button>
          </div>
      </el-card>


    </el-card>

    <!-- Console / Logs -->
    <el-card v-if="logs || isRunning || currentRunId" :style="{'margin-top': '20px', 'background-color': '#1e1e1e', 'border': isCurrentRunSelected ? '2px solid #409EFF' : '1px solid #333', 'color': '#e0e0e0'}">
        <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>
                    <el-icon><Monitor /></el-icon> Terminal Output 
                    <span v-if="currentRunId" style="margin-left: 10px; font-size: 0.9em; color: #aaa;">
                        (Currently Viewing: RunID {{ currentRunId }})
                    </span>
                </span>
                <el-button size="small" type="info" text @click="fetchLogs">Refresh</el-button>
            </div>
        </template>
        <div ref="logContainer" style="height: 300px; overflow-y: auto; font-family: 'Consolas', 'Monaco', monospace; white-space: pre-wrap; font-size: 12px; line-height: 1.4;">
            {{ displayedLogs || 'No logs available for this run.' }}
        </div>
    </el-card>
    
    <!-- Status & Results -->
    <el-card style="margin-top: 20px;" :style="{ border: isCurrentRunSelected ? '1px solid #409EFF' : '' }">
        <template #header>
            <span>
                Run Status: <el-tag>{{ currentRunStatus }}</el-tag>
                <span v-if="currentRunStatus === 'QUEUED' && queuePosition && queuePosition.position > 0" style="margin-left: 10px; font-size: 0.9em; color: #666;">
                    <el-icon><Timer /></el-icon> Queue Position: {{ queuePosition.position }} / {{ queuePosition.total_queued }}
                </span>
            </span>
        </template>
        <div v-if="currentRunStatus === 'SUCCEEDED' || (typeof currentRunStatus === 'string' && currentRunStatus.includes('DEBUG'))">
             <!-- Debug Mode Video -->
             <el-button v-if="currentRunMode === 'debug'" @click="downloadPreview">Download Preview Video</el-button>
             
             <!-- Final Mode CSV -->
             <el-button v-if="currentRunMode === 'final'" type="primary" @click="downloadResult">
                <el-icon style="margin-right: 5px;"><Download /></el-icon> Download CSV
             </el-button>

             <!-- Final Mode Videos -->
             <div v-if="currentRunMode === 'final' && videoArtifacts.length > 0" style="margin-top: 10px;">
                <span style="margin-right: 10px; color: #666; font-size: 14px;">Output Videos:</span>
                <el-button 
                    v-for="vid in videoArtifacts" 
                    :key="vid.path" 
                    size="small" 
                    type="info"
                    plain
                    @click="downloadArtifact(vid.path)"
                >
                    <el-icon style="margin-right: 5px;"><VideoPlay /></el-icon> {{ vid.name }}
                </el-button>
             </div>
        </div>
    </el-card>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VideoPlay, CaretRight, Monitor, QuestionFilled, Download, FullScreen, Timer } from '@element-plus/icons-vue'
import http from '@/api/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { paramGroups } from '@/config/taskParamsSchema'
import defaultParams from '@/config/defaultParams.json'

// --- Helper Functions for Nested Params ---
const getNestedValue = (obj: any, path: string) => {
    if (!obj) return undefined
    return path.split('.').reduce((acc, part) => acc && acc[part], obj)
}

const setNestedValue = (obj: any, path: string, value: any) => {
    const parts = path.split('.')
    let current = obj
    for (let i = 0; i < parts.length - 1; i++) {
        if (!current[parts[i]]) current[parts[i]] = {}
        current = current[parts[i]]
    }
    current[parts[parts.length - 1]] = value
}

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
const logContainer = ref<HTMLElement | null>(null)
let logInterval: any = null
let transferInterval: any = null
const transfer = ref<any>(null)
const transferLastUpdatedAt = ref<number>(0)

const activeNames = ref(['Read']) // Optimized: Only open first group by default
const artifactsLoading = ref(false)
const videoArtifacts = ref<{ path: string; name: string; label?: string }[]>([])
const selectedVideoChannel = ref<'C01' | 'C02'>('C01')

const artifactLoadErrors = ref<string[]>([])
const videoPlayer = ref<HTMLVideoElement | null>(null)
const videoObjectUrl = ref<string>('')
const videoLoadSeq = ref(0)
const videoRetryCount = ref(0)
let videoRetryTimer: any = null

const currentRunMode = computed(() => {
    if (currentRunId.value) {
        const run = history.value.find((r: any) => r.id === currentRunId.value)
        if (run) return run.run_mode
    }
    // Fallback based on params if not linked to a specific run in history yet (e.g. just starting)
    // But be careful, params might change. Best to rely on history.
    return 'unknown'
})

const toggleFullscreen = () => {
    if (videoPlayer.value) {
        if (document.fullscreenElement) {
            document.exitFullscreen()
        } else {
            videoPlayer.value.requestFullscreen()
        }
    }
}

const currentVideo = computed(() => {
    if (!videoArtifacts.value.length) return null
    if (selectedVideoChannel.value === 'C01') {
        return videoArtifacts.value.find(v => /refC01|C01/i.test(v.name)) ?? videoArtifacts.value[0]
    }
    return videoArtifacts.value.find(v => /othC02|C02/i.test(v.name)) ?? videoArtifacts.value[0]
})

const currentVideoUrl = computed(() => videoObjectUrl.value)

const currentVideoName = computed(() => currentVideo.value?.name ?? '')

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
const transferCanCancel = computed(() => {
    const state = transferState.value
    if (!currentRunId.value) return false
    return state === 'transferring' || state === 'queued' || (transferPercent.value !== null && transferPercent.value < 100)
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
        nextTick(() => {
            try {
                videoPlayer.value?.load()
            } catch (e) {
            }
        })
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

        if (videoArtifacts.value.length && selectedVideoChannel.value === 'C02') {
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

// Accessors for Template
const getParamValue = (groupKey: string, paramKey: string) => {
    // Full path is groupKey + '.' + paramKey
    // Exception: If paramKey starts with 'Opts.', it's nested inside groupKey.Opts... which matches logical structure.
    // Actually, backend structure is flat for some, nested for others.
    // Based on MATLAB struct: Cfg.Read.SelectXYs, Cfg.Detect.Opts.bin.sigma
    // So groupKey is top level.
    if (!params.value[groupKey]) return undefined
    return getNestedValue(params.value[groupKey], paramKey)
}

const setParamValue = (groupKey: string, paramKey: string, val: any) => {
    if (!params.value[groupKey]) params.value[groupKey] = {}
    setNestedValue(params.value[groupKey], paramKey, val)
}

const getArrayValueStr = (groupKey: string, paramKey: string) => {
    const val = getParamValue(groupKey, paramKey)
    if (Array.isArray(val)) return val.join(', ')
    return ''
}

const setArrayValueStr = (groupKey: string, paramKey: string, valStr: string, type: 'number' | 'string') => {
    if (!valStr.trim()) {
        setParamValue(groupKey, paramKey, [])
        return
    }
    const arr = valStr.split(',').map(s => s.trim()).filter(s => s !== '')
    if (type === 'number') {
        const numArr = arr.map(Number).filter(n => !isNaN(n))
        setParamValue(groupKey, paramKey, numArr)
    } else {
        setParamValue(groupKey, paramKey, arr)
    }
}

// --- Buffered Input Logic for Arrays ---
const inputBuffer = ref<Record<string, string>>({})
const getUniqueKey = (g: string, p: string) => `${g}.${p}`

const getInputValue = (groupKey: string, paramKey: string) => {
    const k = getUniqueKey(groupKey, paramKey)
    if (inputBuffer.value[k] !== undefined) return inputBuffer.value[k]
    return getArrayValueStr(groupKey, paramKey)
}

const onInputValue = (groupKey: string, paramKey: string, val: string) => {
    const k = getUniqueKey(groupKey, paramKey)
    inputBuffer.value[k] = val
}

const onInputBlur = (groupKey: string, paramKey: string, val: string, type: 'number' | 'string') => {
    setArrayValueStr(groupKey, paramKey, val, type)
    const k = getUniqueKey(groupKey, paramKey)
    // Clear buffer so input reverts to formatted value from store
    delete inputBuffer.value[k]
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

const cancelNd2Transfer = async () => {
    if (!currentRunId.value) return
    try {
        await ElMessageBox.confirm('确认取消当前 ND2 文件传输？', '取消传输', {
            confirmButtonText: '取消传输',
            cancelButtonText: '返回',
            type: 'warning',
        })
    } catch {
        return
    }
    try {
        await http.post(`/tasks/${taskId}/transfer/cancel`, { run_id: currentRunId.value })
        ElMessage.success('已发送取消请求')
        fetchTransferStatus()
        fetchParams()
        fetchHistory()
    } catch (e: any) {
        ElMessage.error('取消失败: ' + (e.response?.data?.detail || e.message))
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
            nextTick(() => {
                if (logContainer.value) {
                    logContainer.value.scrollTop = logContainer.value.scrollHeight
                }
            })
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
    if (currentRunStatus.value === 'SUCCEEDED' && currentRunMode.value === 'final' && !videoArtifacts.value.length) {
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
.run-controls {
    margin-top: 30px;
}
.control-row {
    display: flex;
    align-items: center;
    gap: 20px;
}
.param-editor {
    margin-bottom: 30px;
}
</style>
