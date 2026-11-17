<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <header class="topbar">
    <div class="container">
      <RouterLink to="/campaigns" class="brand">Keitaro · Editor</RouterLink>
      <RouterLink to="/campaigns" class="nav-link" active-class="is-active">Кампании</RouterLink>
      <RouterLink to="/create" class="nav-link" active-class="is-active">Новая кампания</RouterLink>
    </div>
  </header>
  <main class="container page">
    <RouterView />
  </main>
</template>
