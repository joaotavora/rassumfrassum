<script setup lang="ts">
const greeting: string = 'Hello from Vue'

function shout(s: string): string {
  return s.toUpperCase()
}
</script>

<template>
  <div class="p-4">
    <h1>{{ shout(greeting) }}</h1>
  </div>
</template>
