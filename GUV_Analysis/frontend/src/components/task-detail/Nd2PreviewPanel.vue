<template>
  <el-card v-loading="loading">
    <template #header>
      <div class="panel-header">
        <span>ND2 Preview</span>
        <el-button size="small" @click="$emit('refresh-fast')">Refresh</el-button>
      </div>
    </template>

    <el-alert v-if="error" :title="error" type="warning" :closable="false" show-icon />
    <div v-else>
      <div class="preview-controls">
        <span class="control-label">视野</span>
        <el-select :model-value="series" size="small" class="series-select" @update:model-value="$emit('update:series', Number($event))" @change="$emit('series-change')">
          <el-option
            v-for="s in seriesOptions"
            :key="s.index"
            :label="formatSeriesLabel(s)"
            :value="s.index"
          />
        </el-select>

        <span class="control-label">模式</span>
        <el-radio-group :model-value="previewMode" size="small" @update:model-value="$emit('update:previewMode', String($event) === 'merge' ? 'merge' : 'single')" @change="$emit('control-change')">
          <el-radio-button label="single">单通道</el-radio-button>
          <el-radio-button label="merge" :disabled="channelOptions.length < 2">Merge</el-radio-button>
        </el-radio-group>

        <span class="control-label">通道</span>
        <el-select :model-value="c" size="small" class="channel-select" @update:model-value="$emit('update:c', Number($event))" @change="$emit('control-change')">
          <el-option v-for="ch in channelOptions" :key="ch.value" :label="ch.label" :value="ch.value" />
        </el-select>
        <el-select
          v-if="previewMode === 'merge'"
          :model-value="c2"
          size="small"
          class="channel-select"
          @update:model-value="$emit('update:c2', Number($event))"
          @change="$emit('control-change')"
        >
          <el-option v-for="ch in channelOptions" :key="ch.value" :label="ch.label" :value="ch.value" />
        </el-select>

        <span v-if="maxZ > 0" class="control-label">Z</span>
        <el-input-number v-if="maxZ > 0" :model-value="z" size="small" :min="0" :max="maxZ" @update:model-value="$emit('update:z', Number($event))" @change="$emit('control-change')" />

        <span v-if="maxT > 0" class="control-label">T</span>
        <el-input-number v-if="maxT > 0" :model-value="t" size="small" :min="0" :max="maxT" @update:model-value="$emit('update:t', Number($event))" @change="$emit('control-change')" />

        <span class="control-label">伪色</span>
        <el-select :model-value="lut" size="small" class="lut-select" @update:model-value="$emit('update:lut', String($event))" @change="$emit('control-change')">
          <el-option label="Gray" value="gray" />
          <el-option label="Green" value="green" />
          <el-option label="Red" value="red" />
          <el-option label="Magenta" value="magenta" />
          <el-option label="Cyan" value="cyan" />
        </el-select>
        <el-select
          v-if="previewMode === 'merge'"
          :model-value="lut2"
          size="small"
          class="lut-select"
          @update:model-value="$emit('update:lut2', String($event))"
          @change="$emit('control-change')"
        >
          <el-option label="Gray" value="gray" />
          <el-option label="Green" value="green" />
          <el-option label="Red" value="red" />
          <el-option label="Magenta" value="magenta" />
          <el-option label="Cyan" value="cyan" />
        </el-select>

        <el-tag size="small" :type="quality === 'full' ? 'success' : 'info'">
          {{ quality === 'full' ? '高清' : '快速' }}
        </el-tag>
        <el-button size="small" :disabled="quality === 'full' || loading" @click="$emit('load-full')">
          高清查看
        </el-button>
      </div>

      <div v-if="previewUrl" class="preview-image-wrap">
        <img :src="previewUrl" class="preview-image" />
      </div>
      <el-empty v-else description="No preview loaded" />
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineProps<{
  loading: boolean
  error: string
  series: number
  seriesOptions: any[]
  z: number
  c: number
  c2: number
  t: number
  lut: string
  lut2: string
  previewMode: 'single' | 'merge'
  quality: 'fast' | 'full'
  maxZ: number
  maxT: number
  channelOptions: Array<{ value: number; label: string }>
  previewUrl: string
  formatSeriesLabel: (series: any) => string
}>()

defineEmits<{
  (e: 'update:series', value: number): void
  (e: 'update:z', value: number): void
  (e: 'update:c', value: number): void
  (e: 'update:c2', value: number): void
  (e: 'update:t', value: number): void
  (e: 'update:lut', value: string): void
  (e: 'update:lut2', value: string): void
  (e: 'update:previewMode', value: 'single' | 'merge'): void
  (e: 'refresh-fast'): void
  (e: 'load-full'): void
  (e: 'control-change'): void
  (e: 'series-change'): void
}>()
</script>

<style scoped>
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.preview-controls {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 12px;
}

.control-label {
  font-size: 13px;
  color: #666;
}

.series-select {
  width: 180px;
}

.channel-select {
  width: 130px;
}

.lut-select {
  width: 120px;
}

.preview-image-wrap {
  max-width: 900px;
  background: #111;
  padding: 8px;
}

.preview-image {
  display: block;
  width: 100%;
  max-height: 620px;
  object-fit: contain;
}
</style>
