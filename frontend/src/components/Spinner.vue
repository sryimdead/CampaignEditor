<script setup>
// Индикатор загрузки. Используется и в кнопках, и в блоках, и поверх таблиц.
defineProps({
  size: { type: Number, default: 16 },
  label: { type: String, default: 'Загрузка' },
})
</script>

<template>
  <span
    class="spinner"
    role="status"
    :aria-label="label"
    :style="{ width: size + 'px', height: size + 'px', borderWidth: Math.max(2, Math.round(size / 8)) + 'px' }"
  ></span>
</template>
