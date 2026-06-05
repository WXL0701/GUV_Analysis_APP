<template>
  <el-card v-if="visible" class="terminal-card" :style="{ border }">
    <template #header>
      <div class="terminal-header">
        <span>
          <el-icon><Monitor /></el-icon> Terminal Output
          <span v-if="currentRunId" class="run-id">
            (Currently Viewing: RunID {{ currentRunId }})
          </span>
        </span>
        <el-button size="small" type="info" text @click="$emit('refresh')">Refresh</el-button>
      </div>
    </template>
    <div ref="logContainer" class="terminal-output">
      {{ displayedLogs || 'No logs available for this run.' }}
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Monitor } from '@element-plus/icons-vue'

const props = defineProps<{
  visible: boolean
  displayedLogs: string
  currentRunId: string | null
  isCurrentRunSelected: boolean
}>()

defineEmits<{
  (e: 'refresh'): void
}>()

const logContainer = ref<HTMLElement | null>(null)
const border = computed(() => props.isCurrentRunSelected ? '2px solid #409EFF' : '1px solid #333')

watch(
  () => props.displayedLogs,
  () => {
    nextTick(() => {
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight
      }
    })
  },
)
</script>

<style scoped>
.terminal-card {
  margin-top: 20px;
  background-color: #1e1e1e;
  color: #e0e0e0;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.run-id {
  margin-left: 10px;
  font-size: 0.9em;
  color: #aaa;
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
