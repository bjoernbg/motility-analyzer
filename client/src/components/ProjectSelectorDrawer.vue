<script setup lang="ts">
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from 'reka-ui';
import { Button } from './ui/button';
import { Icon } from './ui/icon';
import WorkspaceEntitySelector from './WorkspaceEntitySelector.vue';

const open = defineModel<boolean>('open', {
  default: false,
});

const emit = defineEmits<{
  'create-combined': [];
  'entity-selected': [{ type: 'video' | 'combined'; id: string }];
}>();
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogPortal>
      <DialogOverlay class="project-drawer-overlay" />
      <DialogContent class="project-drawer-content">
        <div class="project-drawer-header">
          <div class="project-drawer-heading">
            <DialogTitle class="project-drawer-title">Projects</DialogTitle>
            <DialogDescription class="project-drawer-description">
              Choose a video or combined analysis without leaving the current workspace.
            </DialogDescription>
          </div>

          <DialogClose as-child>
            <Button aria-label="Close project drawer" size="icon-sm" variant="ghost">
              <Icon name="lucide:x" size="1rem" />
            </Button>
          </DialogClose>
        </div>

        <div class="project-drawer-body">
          <WorkspaceEntitySelector
            @create-combined="emit('create-combined')"
            @entity-selected="emit('entity-selected', $event)"
          />
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.project-drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.44);
  z-index: 1800;
}

.project-drawer-content {
  position: fixed;
  inset: 0 auto 0 0;
  width: clamp(340px, 28vw, 420px);
  max-width: 100vw;
  height: 100vh;
  border-right: 1px solid var(--border-light);
  background: var(--bg-secondary);
  box-shadow: 24px 0 48px rgba(15, 23, 42, 0.18);
  z-index: 1900;
  display: flex;
  flex-direction: column;
  outline: none;
}

.project-drawer-content[data-state='open'] {
  animation: slide-in 0.22s ease-out;
}

.project-drawer-content[data-state='closed'] {
  animation: slide-out 0.18s ease-in;
}

.project-drawer-overlay[data-state='open'] {
  animation: fade-in 0.18s ease-out;
}

.project-drawer-overlay[data-state='closed'] {
  animation: fade-out 0.14s ease-in;
}

.project-drawer-header {
  padding: 1rem 1rem 0.9rem;
  border-bottom: 1px solid var(--border-light);
  background: var(--bg-primary);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.project-drawer-heading {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.project-drawer-title,
.project-drawer-description {
  margin: 0;
}

.project-drawer-title {
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-primary);
}

.project-drawer-description {
  font-size: 0.84rem;
  color: var(--text-secondary);
}

.project-drawer-body {
  flex: 1;
  overflow: auto;
  padding: 1rem;
}

@keyframes slide-in {
  from {
    transform: translateX(-24px);
    opacity: 0;
  }

  to {
    transform: translateX(0);
    opacity: 1;
  }
}

@keyframes slide-out {
  from {
    transform: translateX(0);
    opacity: 1;
  }

  to {
    transform: translateX(-18px);
    opacity: 0;
  }
}

@keyframes fade-in {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

@keyframes fade-out {
  from {
    opacity: 1;
  }

  to {
    opacity: 0;
  }
}

@media (max-width: 768px) {
  .project-drawer-content {
    width: 100vw;
  }
}
</style>
