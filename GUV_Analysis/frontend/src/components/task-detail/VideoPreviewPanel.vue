<template>
  <el-card v-if="visible" class="video-card" v-loading="loading">
    <template #header>
      <div class="panel-header">
        <span>{{ currentRunMode === 'video' ? 'Generated Video Preview' : 'Debug Video Preview' }}</span>
        <el-button size="small" @click="$emit('refresh')">Refresh</el-button>
      </div>
    </template>

    <el-empty v-if="videoArtifacts.length === 0" :description="currentRunMode === 'video' ? 'No generated videos found' : 'No debug videos found'" />
    <div v-else>
      <div class="video-controls">
        <el-radio-group :model-value="selectedVideoChannel" @update:model-value="$emit('update:selectedVideoChannel', normalizeChannel($event))">
          <el-radio-button label="C01">Channel C01 (Ref)</el-radio-button>
          <el-radio-button label="C02">Channel C02</el-radio-button>
          <el-radio-button v-if="hasMergeVideo" label="MERGE">Merge</el-radio-button>
        </el-radio-group>
        <el-button :icon="FullScreen" circle title="Toggle Fullscreen" @click="toggleFullscreen" />
      </div>

      <div v-if="currentVideoUrl" class="video-wrap">
        <video
          ref="videoPlayer"
          :key="currentVideoUrl"
          controls
          class="video-player"
          @error="$emit('video-error')"
        >
          <source :src="currentVideoUrl" :type="currentVideoMime">
          Your browser does not support the video tag.
        </video>
        <div class="playing-label">
          Playing: {{ currentVideoName }}
        </div>
      </div>
      <el-alert v-else title="Video for selected channel not found." type="warning" show-icon :closable="false" />

      <div v-if="downloadOnlyVideos.length > 0" class="download-only">
        <span class="download-only-label">Download-only videos:</span>
        <el-button
          v-for="vid in downloadOnlyVideos"
          :key="vid.path"
          size="small"
          @click="$emit('download-artifact', vid.path)"
        >
          {{ vid.name }}
        </el-button>
      </div>
    </div>

    <div v-if="artifactLoadErrors.length > 0" class="error-list">
      <el-alert
        v-for="(err, idx) in artifactLoadErrors"
        :key="idx"
        :title="err"
        type="error"
        show-icon
        class="error-item"
      />
      <el-button type="danger" size="small" @click="$emit('retry')">Retry Connection</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { FullScreen } from '@element-plus/icons-vue'

type VideoChannel = 'C01' | 'C02' | 'MERGE'
type VideoArtifact = {
  path: string
  name: string
  playable?: boolean
}

const props = defineProps<{
  visible: boolean
  loading: boolean
  currentRunMode: string
  videoArtifacts: VideoArtifact[]
  selectedVideoChannel: VideoChannel
  hasMergeVideo: boolean
  currentVideoUrl: string
  currentVideoMime: string
  currentVideoName: string
  downloadOnlyVideos: VideoArtifact[]
  artifactLoadErrors: string[]
}>()

defineEmits<{
  (e: 'update:selectedVideoChannel', value: VideoChannel): void
  (e: 'refresh'): void
  (e: 'retry'): void
  (e: 'video-error'): void
  (e: 'download-artifact', path: string): void
}>()

const videoPlayer = ref<HTMLVideoElement | null>(null)

const normalizeChannel = (value: any): VideoChannel => {
  if (value === 'MERGE') return 'MERGE'
  if (value === 'C02') return 'C02'
  return 'C01'
}

const toggleFullscreen = () => {
  if (!videoPlayer.value) return
  if (document.fullscreenElement) {
    document.exitFullscreen()
  } else {
    videoPlayer.value.requestFullscreen()
  }
}

watch(
  () => props.currentVideoUrl,
  () => {
    nextTick(() => {
      try {
        videoPlayer.value?.load()
      } catch (e) {
      }
    })
  },
)
</script>

<style scoped>
.video-card {
  margin-top: 20px;
}

.panel-header,
.video-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.video-controls {
  margin-bottom: 15px;
}

.video-wrap {
  max-width: 800px;
  margin: 0 auto;
}

.video-player {
  width: 100%;
  border-radius: 4px;
  background: #000;
}

.playing-label {
  margin-top: 10px;
  text-align: center;
  color: #666;
}

.download-only {
  margin-top: 12px;
}

.download-only-label {
  margin-right: 10px;
  color: #666;
  font-size: 13px;
}

.error-list {
  margin-top: 20px;
}

.error-item {
  margin-bottom: 5px;
}
</style>
