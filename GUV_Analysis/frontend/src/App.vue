<template>
  <el-container class="layout-container">
    <el-aside width="220px" class="aside-menu">
      <div class="logo">
        <el-icon :size="24" color="#409EFF"><Monitor /></el-icon>
        <span class="title">GUV Analysis</span>
      </div>
      <el-menu 
        router 
        :default-active="$route.path"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
        class="el-menu-vertical"
      >
        <el-menu-item index="/">
          <el-icon><Odometer /></el-icon>
          <span>Dashboard</span>
        </el-menu-item>
        <el-menu-item index="/tasks/create">
          <el-icon><Plus /></el-icon>
          <span>New Task</span>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><List /></el-icon>
          <span>History</span>
        </el-menu-item>
        <el-menu-item index="/tasks/queue">
          <el-icon><Operation /></el-icon>
          <span>Queue & Progress</span>
        </el-menu-item>
        <el-menu-item index="/system">
          <el-icon><Cpu /></el-icon>
          <span>System Monitor</span>
        </el-menu-item>
        <el-menu-item index="/system/config" v-if="userStore.role === 'admin'">
          <el-icon><Setting /></el-icon>
          <span>System Config</span>
        </el-menu-item>
        <el-menu-item index="/users" v-if="userStore.role === 'admin'">
          <el-icon><User /></el-icon>
          <span>Users</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    
    <el-container>
      <el-header class="main-header">
        <div class="breadcrumb">
          <!-- Optional Breadcrumb -->
        </div>
        <div class="toolbar">
          <el-dropdown @command="handleCommand">
            <div class="user-profile">
              <el-avatar :size="32" :icon="UserFilled" />
              <span class="username">{{ username }}</span>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">Logout</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Monitor, Plus, List, Setting, User, Odometer, Cpu, UserFilled, Operation } from '@element-plus/icons-vue'
import http from '@/api/http'

const router = useRouter()
const username = ref('User')
const userStore = ref({ role: 'user' })

const updateUsername = async () => {
  // First try to get from sessionStorage for immediate feedback
  const stored = sessionStorage.getItem('username')
  if (stored) {
    username.value = stored
  }
  
  // Then fetch from API to be sure
  const token = sessionStorage.getItem('token')
  if (token) {
    try {
        const { data } = await http.get('/users/me')
        username.value = data.username
        userStore.value = { role: data.role }
        sessionStorage.setItem('username', data.username)
    } catch (e) {
        // If 401, clear token? 
        // For now just ignore
    }
  }
}

onMounted(() => {
  // Clear legacy localStorage auth data to prevent confusion
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  updateUsername()
})

// Watch for route changes to update username (e.g. after login)
import { watch } from 'vue'
watch(() => router.currentRoute.value, () => {
  updateUsername()
})

const handleCommand = (command: string) => {
  if (command === 'logout') {
    sessionStorage.removeItem('token')
    sessionStorage.removeItem('username')
    router.push('/login')
  }
}
</script>

<style>
body {
  margin: 0;
  padding: 0;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}

.layout-container {
  height: 100vh;
}

.aside-menu {
  background-color: #304156;
  color: #fff;
  display: flex;
  flex-direction: column;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background-color: #2b3649;
  color: #fff;
  font-weight: bold;
  font-size: 18px;
}

.el-menu-vertical {
  border-right: none !important;
}

.main-header {
  background-color: #fff;
  box-shadow: 0 1px 4px rgba(0,21,41,.08);
  display: flex;
  justify-content: flex-end; /* Align user to right */
  align-items: center;
  padding: 0 20px;
  height: 60px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.user-profile {
  display: flex;
  align-items: center;
  cursor: pointer;
  gap: 8px;
}

.username {
  font-size: 14px;
  color: #333;
}

.main-content {
  background-color: #f0f2f5;
  padding: 20px;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
