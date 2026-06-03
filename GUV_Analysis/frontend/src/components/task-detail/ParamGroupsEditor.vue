<template>
  <div class="param-editor">
    <el-form v-if="showGlobal" label-position="top">
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
      <el-divider />
    </el-form>

    <el-collapse :model-value="activeNames" @update:model-value="(val: any) => $emit('update:activeNames', val)">
      <el-collapse-item v-for="group in groups" :key="group.key" :title="group.label" :name="group.key">
        <el-form label-position="left" label-width="200px">
          <el-row :gutter="24">
            <el-col :span="12" v-for="param in group.params" :key="param.key">
              <el-form-item>
                <template #label>
                  <div class="field-label">
                    {{ param.label }}
                    <el-tooltip :content="param.tooltip" placement="top">
                      <el-icon><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </div>
                </template>

                <el-input-number
                  v-if="param.type === 'number'"
                  :model-value="getParamValue(group.key, param.key)"
                  @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                  :step="param.step || 1"
                />

                <div v-else-if="param.type === 'slider'" class="slider-field">
                  <el-slider
                    :model-value="getParamValue(group.key, param.key)"
                    @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                    :min="param.min"
                    :max="param.max"
                    :step="param.step"
                    class="slider-input"
                  />
                  <el-input-number
                    :model-value="getParamValue(group.key, param.key)"
                    @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                    :step="param.step"
                    size="small"
                    class="slider-number"
                  />
                </div>

                <el-switch
                  v-else-if="param.type === 'boolean'"
                  :model-value="getParamValue(group.key, param.key)"
                  @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                />

                <el-input
                  v-else-if="param.type === 'text'"
                  :model-value="getParamValue(group.key, param.key)"
                  @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                />

                <el-select
                  v-else-if="param.type === 'select'"
                  :model-value="getParamValue(group.key, param.key)"
                  @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                >
                  <el-option v-for="opt in param.options" :key="opt" :label="opt" :value="opt" />
                </el-select>

                <el-select
                  v-else-if="param.type === 'multi_select'"
                  :model-value="getParamValue(group.key, param.key)"
                  @update:model-value="(val: any) => setParamValue(group.key, param.key, val)"
                  multiple
                  collapse-tags
                  collapse-tags-tooltip
                >
                  <el-option v-for="opt in param.options" :key="opt" :label="opt" :value="opt" />
                </el-select>

                <el-input
                  v-else-if="param.type === 'array_number'"
                  :model-value="getInputValue(group.key, param.key)"
                  @input="(val: string) => onInputValue(group.key, param.key, val)"
                  @change="(val: string) => onInputBlur(group.key, param.key, val, 'number')"
                  placeholder="e.g. 1, 2, 5"
                />

                <el-input
                  v-else-if="param.type === 'array_select'"
                  :model-value="getInputValue(group.key, param.key)"
                  @input="(val: string) => onInputValue(group.key, param.key, val)"
                  @change="(val: string) => onInputBlur(group.key, param.key, val, 'string')"
                  placeholder="e.g. inner, mem"
                />

                <el-select
                  v-else-if="param.type === 'array_string'"
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
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </el-collapse-item>

      <el-collapse-item v-if="showAdvanced" title="Advanced Configuration (JSON)" name="advanced">
        <el-alert title="Edit raw JSON for full control." type="info" :closable="false" class="json-alert" />
        <el-input
          :model-value="paramsJson"
          type="textarea"
          :rows="15"
          @update:model-value="(val: string) => $emit('update:paramsJson', val)"
          @change="$emit('sync-json')"
          placeholder="Loading parameters..."
        />
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import type { ParamGroup } from '@/config/taskParamsSchema'

const props = withDefaults(defineProps<{
  groups: ParamGroup[]
  params: any
  activeNames: string[]
  paramsJson?: string
  showGlobal?: boolean
  showAdvanced?: boolean
}>(), {
  paramsJson: '',
  showGlobal: false,
  showAdvanced: false,
})

defineEmits<{
  (e: 'update:activeNames', value: string[]): void
  (e: 'update:paramsJson', value: string): void
  (e: 'sync-json'): void
}>()

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

const getParamValue = (groupKey: string, paramKey: string) => {
  if (!props.params[groupKey]) return undefined
  return getNestedValue(props.params[groupKey], paramKey)
}

const setParamValue = (groupKey: string, paramKey: string, val: any) => {
  if (!props.params[groupKey]) props.params[groupKey] = {}
  setNestedValue(props.params[groupKey], paramKey, val)
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
    setParamValue(groupKey, paramKey, arr.map(Number).filter(n => !isNaN(n)))
  } else {
    setParamValue(groupKey, paramKey, arr)
  }
}

const inputBuffer = ref<Record<string, string>>({})
const getUniqueKey = (g: string, p: string) => `${g}.${p}`

const getInputValue = (groupKey: string, paramKey: string) => {
  const k = getUniqueKey(groupKey, paramKey)
  if (inputBuffer.value[k] !== undefined) return inputBuffer.value[k]
  return getArrayValueStr(groupKey, paramKey)
}

const onInputValue = (groupKey: string, paramKey: string, val: string) => {
  inputBuffer.value[getUniqueKey(groupKey, paramKey)] = val
}

const onInputBlur = (groupKey: string, paramKey: string, val: string, type: 'number' | 'string') => {
  setArrayValueStr(groupKey, paramKey, val, type)
  delete inputBuffer.value[getUniqueKey(groupKey, paramKey)]
}
</script>

<style scoped>
.param-editor {
  margin-bottom: 30px;
}

.field-label {
  display: flex;
  align-items: center;
  gap: 5px;
}

.slider-field {
  display: flex;
  align-items: center;
  width: 100%;
}

.slider-input {
  flex-grow: 1;
  margin-right: 15px;
}

.slider-number {
  width: 100px;
}

.json-alert {
  margin-bottom: 10px;
}
</style>
