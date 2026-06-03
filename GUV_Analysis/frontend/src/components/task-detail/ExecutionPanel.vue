<template>
  <div class="run-controls">
    <el-divider content-position="left">Execution</el-divider>
    <div class="control-row">
      <div v-if="params.Debug?.Enable" class="mode-action">
        <el-alert
          title="Debug Mode: Runs on a single XY position to generate a preview video."
          type="info"
          show-icon
          :closable="false"
          class="mode-alert"
        />
        <el-button type="warning" :disabled="isRunning" size="large" @click="$emit('run-debug')">
          <el-icon><VideoPlay /></el-icon> Run Debug (Preview)
        </el-button>
      </div>

      <div v-else class="mode-action">
        <el-alert
          title="Final Mode: Runs full analysis on all positions and generates CSV results."
          type="success"
          show-icon
          :closable="false"
          class="mode-alert"
        />
        <el-button type="success" :disabled="isRunning" size="large" @click="$emit('run-final')">
          <el-icon><CaretRight /></el-icon> Run Final Analysis
        </el-button>
      </div>

      <div class="mode-action video-action">
        <el-alert
          title="Video Mode: Generates C1/C2/Merge MP4 directly from ND2 without MATLAB analysis or CSV output."
          type="info"
          show-icon
          :closable="false"
          class="video-alert"
        />
        <el-button type="primary" :disabled="isRunning" size="large" @click="$emit('run-video')">
          <el-icon><VideoPlay /></el-icon> 生成视频
        </el-button>
      </div>
    </div>

    <el-card v-if="transferVisible" class="transfer-card">
      <template #header>
        <div class="transfer-header">
          <span>ND2 后台状态</span>
        </div>
      </template>
      <div class="transfer-row">
        <el-tag :type="transferTagType">{{ transferLabel }}</el-tag>
        <div v-if="transferState === 'failed'" class="transfer-error">
          <el-alert :title="transferDetailText" type="error" :closable="false" show-icon class="break-text" />
        </div>
        <span v-else class="muted">{{ transferDetailText }}</span>
      </div>
      <div v-if="typeof transferPercent === 'number'" class="progress-row">
        <el-progress :percentage="transferPercent" :status="transferProgressStatus" />
      </div>
      <div v-if="coldArchiveDetailText" class="cold-detail">
        冷盘归档：{{ coldArchiveDetailText }}
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { CaretRight, VideoPlay } from '@element-plus/icons-vue'

defineProps<{
  params: any
  isRunning: boolean
  transferVisible: boolean
  transferTagType: string
  transferLabel: string
  transferState: string
  transferDetailText: string
  transferPercent: number | null
  transferProgressStatus?: string
  coldArchiveDetailText: string
}>()

defineEmits<{
  (e: 'run-debug'): void
  (e: 'run-final'): void
  (e: 'run-video'): void
}>()
</script>

<style scoped>
.run-controls {
  margin-top: 30px;
}

.control-row {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  flex-wrap: wrap;
}

.mode-action {
  display: flex;
  gap: 20px;
  align-items: center;
}

.video-action {
  margin-top: 12px;
}

.mode-alert {
  width: 400px;
}

.video-alert {
  width: 520px;
}

.transfer-card {
  margin-top: 12px;
}

.transfer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.transfer-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.transfer-error {
  flex: 1;
  min-width: 300px;
}

.break-text {
  word-break: break-all;
}

.muted,
.cold-detail {
  color: #666;
  font-size: 12px;
}

.progress-row,
.cold-detail {
  margin-top: 10px;
}
</style>
