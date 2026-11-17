<script setup>
import { ref, computed } from 'vue'

// Поле со списком: фокус или ввод открывают выпадающий список с поиском,
// выбор записывает оффер в это же поле и закрывает список.
const props = defineProps({
  modelValue: { type: Number, default: null },
  options: { type: Array, required: true }, // [{ id, name }]
  loading: { type: Boolean, default: false },
  placeholder: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const inputEl = ref(null)
const open = ref(false)
const query = ref('')
const active = ref(-1)

const label = (o) => `#${o.id} · ${o.name}`
const selected = computed(() => props.options.find((o) => o.id === props.modelValue) || null)

// Пока список открыт, в поле показываем текст поиска; закрытым - выбранный оффер.
const displayValue = computed(() => {
  if (open.value) return query.value
  return selected.value ? label(selected.value) : ''
})

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return props.options
  return props.options.filter(
    (o) => String(o.id).includes(q) || o.name.toLowerCase().includes(q),
  )
})

function openList() {
  if (props.loading) return
  open.value = true
  query.value = ''
  active.value = -1
}

function onInput(event) {
  query.value = event.target.value
  open.value = true
  active.value = -1
}

function choose(o) {
  emit('update:modelValue', o.id)
  open.value = false
  query.value = ''
  active.value = -1
  inputEl.value?.blur()
}

function closeList() {
  open.value = false
  query.value = ''
  active.value = -1
}

function onKeydown(event) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (!open.value) return openList()
    active.value = Math.min(active.value + 1, filtered.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    active.value = Math.max(active.value - 1, 0)
  } else if (event.key === 'Enter') {
    if (open.value && active.value >= 0 && filtered.value[active.value]) {
      event.preventDefault()
      choose(filtered.value[active.value])
    }
  } else if (event.key === 'Escape') {
    closeList()
  }
}
</script>

<template>
  <div class="combo">
    <input
      ref="inputEl"
      type="text"
      role="combobox"
      autocomplete="off"
      :aria-expanded="open"
      :value="displayValue"
      :placeholder="loading ? 'Загрузка офферов…' : placeholder"
      :disabled="loading"
      @focus="openList"
      @click="openList"
      @input="onInput"
      @blur="closeList"
      @keydown="onKeydown"
    />
    <ul v-if="open" class="combo-list" role="listbox">
      <li
        v-for="(o, i) in filtered"
        :key="o.id"
        role="option"
        :aria-selected="o.id === modelValue"
        :class="{ active: i === active, selected: o.id === modelValue }"
        @mousedown.prevent="choose(o)"
        @mouseenter="active = i"
      >
        {{ label(o) }}
      </li>
      <li v-if="!filtered.length" class="empty">Ничего не найдено</li>
    </ul>
  </div>
</template>
