<script setup>
import { FolderGit2, LogOut } from "@lucide/vue";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { LOGIN_URL } from "@/api/github";

defineProps({
  connection: { type: Object, required: true },
  busy: { type: Boolean, default: false },
});
defineEmits(["disconnect"]);

function when(value) {
  if (!value) return "";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
</script>

<template>
  <p v-if="!connection.available" class="flex items-center gap-2 text-sm text-muted-foreground">
    <FolderGit2 class="size-4" />
    GitHub sign-in isn't configured on this deployment.
  </p>

  <Button v-else-if="!connection.connected" as-child size="sm">
    <a :href="LOGIN_URL">
      <FolderGit2 class="size-4" />
      Connect GitHub
    </a>
  </Button>

  <div v-else class="flex items-center gap-3">
    <Avatar>
      <AvatarImage :src="connection.avatar_url" alt="" />
      <AvatarFallback>{{ connection.login?.[0]?.toUpperCase() }}</AvatarFallback>
    </Avatar>
    <div class="text-sm">
      <p class="font-medium leading-none">{{ connection.login }}</p>
      <p class="mt-1 text-xs text-muted-foreground">
        Access expires {{ when(connection.expires_at) }}
      </p>
    </div>
    <Button
      variant="ghost"
      size="icon"
      :disabled="busy"
      title="Disconnect"
      @click="$emit('disconnect')"
    >
      <LogOut class="size-4" />
    </Button>
  </div>
</template>
