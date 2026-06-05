<template>
  <el-card class="status-card" :style="{ border: isCurrentRunSelected ? '1px solid #409EFF' : '' }">
    <template #header>
      <span>
        Run Status: <el-tag>{{ currentRunStatus }}</el-tag>
        <span
          v-if="currentRunStatus === 'QUEUED' && queuePosition && queuePosition.position > 0"
          class="queue-position"
        >
          <el-icon><Timer /></el-icon> Queue Position:
          {{ queuePosition.position }} / {{ queuePosition.total_queued }}
        </span>
      </span>
    </template>
    <div v-if="showResults">
      <el-button type="success" @click="$emit('download-all')">
        <el-icon class="button-icon"><Download /></el-icon> 一键下载结果
      </el-button>

      <el-button v-if="currentRunMode === 'debug'" @click="$emit('download-preview')">
        下载预览视频
      </el-button>

      <el-button v-if="currentRunMode === 'final'" type="primary" @click="$emit('download-result')">
        <el-icon class="button-icon"><Download /></el-icon> 下载 CSV
      </el-button>

      <div v-if="(currentRunMode === 'final' || currentRunMode === 'video') && videoArtifacts.length > 0" class="video-list">
        <span class="video-list-label">输出视频:</span>
        <el-button
          v-for="vid in videoArtifacts"
          :key="vid.path"
          size="small"
          type="info"
          plain
          @click="$emit('download-artifact', vid.path)"
        >
          <el-icon class="button-icon"><VideoPlay /></el-icon> {{ vid.name }}
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Download, Timer, VideoPlay } from '@element-plus/icons-vue'

const props = defineProps<{
  currentRunStatus: string
  currentRunMode: string
  queuePosition: { status: string; position: number; total_queued: number } | null
  isCurrentRunSelected: boolean
  videoArtifacts: Array<{ path: string; name: string }>
}>()

defineEmits<{
  (e: 'download-all'): void
  (e: 'download-preview'): void
  (e: 'download-result'): void
  (e: 'download-artifact', path: string): void
}>()

const showResults = computed(() => {
  return props.currentRunStatus === 'SUCCEEDED' || props.currentRunStatus.includes('DEBUG')
})
</script>

<style scoped>
.status-card {
  margin-top: 20px;
}

.queue-position {
  margin-left: 10px;
  font-size: 0.9em;
  color: #666;
}

.button-icon {
  margin-right: 5px;
}

.video-list {
  margin-top: 10px;
}

.video-list-label {
  margin-right: 10px;
  color: #666;
  font-size: 14px;
}
</style>
