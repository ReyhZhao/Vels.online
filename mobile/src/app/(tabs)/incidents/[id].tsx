import { useCallback, useEffect, useState } from 'react';
import {
  Alert as RNAlert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Stack, useLocalSearchParams } from 'expo-router';
import { CheckCircle2, Circle, Send } from 'lucide-react-native';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { KeyValue, SectionHeader } from '@/components/KeyValue';
import { Segmented } from '@/components/Segmented';
import { ErrorState, LoadingView } from '@/components/States';
import api from '@/lib/api';
import { formatDateTime, humanize, timeAgo } from '@/lib/format';
import { severityColor, stateColor } from '@/lib/labels';
import { colors, fontSize, radius, spacing } from '@/lib/theme';
import { allowedTransitions, CLOSURE_REASONS } from '@/lib/transitions';
import type { Comment, Incident, IncidentTask } from '@/lib/types';

const TABS = ['overview', 'comments', 'tasks'] as const;

export default function IncidentDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [tab, setTab] = useState<string>('overview');

  const load = useCallback(
    async ({ refreshing = false } = {}) => {
      if (refreshing) setIsRefreshing(true);
      try {
        const res = await api.get(`/api/incidents/${id}/`);
        setIncident(res.data);
        setError(null);
      } catch (err: any) {
        setError(err?.response?.data?.detail ?? 'Could not load incident.');
      } finally {
        setIsRefreshing(false);
      }
    },
    [id],
  );

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorState message={error} />;
  if (!incident) return <LoadingView />;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      <Stack.Screen options={{ title: incident.display_id }} />
      <View style={styles.header}>
        <Text style={styles.title}>{incident.title}</Text>
        <View style={styles.badges}>
          <Badge label={incident.severity} color={severityColor(incident.severity)} />
          <Badge label={incident.state} color={stateColor(incident.state)} />
          {incident.org_name ? <Badge label={incident.org_name} /> : null}
        </View>
      </View>
      <Segmented
        options={TABS}
        labels={{
          overview: 'Overview',
          comments: `Comments`,
          tasks: `Tasks (${incident.task_count})`,
        }}
        selected={tab}
        onSelect={setTab}
      />
      {tab === 'overview' && (
        <OverviewTab incident={incident} onChanged={() => load()} isRefreshing={isRefreshing} onRefresh={() => load({ refreshing: true })} />
      )}
      {tab === 'comments' && <CommentsTab displayId={incident.display_id} />}
      {tab === 'tasks' && <TasksTab displayId={incident.display_id} />}
    </KeyboardAvoidingView>
  );
}

function OverviewTab({
  incident,
  onChanged,
  isRefreshing,
  onRefresh,
}: {
  incident: Incident;
  onChanged: () => void;
  isRefreshing: boolean;
  onRefresh: () => void;
}) {
  const [transitioning, setTransitioning] = useState<string | null>(null);

  async function transition(state: string, closureReason?: string) {
    setTransitioning(state);
    try {
      await api.post(`/api/incidents/${incident.display_id}/transition/`, {
        state,
        ...(closureReason ? { closure_reason: closureReason } : {}),
      });
      onChanged();
    } catch (err: any) {
      RNAlert.alert('Transition failed', err?.response?.data?.detail ?? 'Please try again.');
    } finally {
      setTransitioning(null);
    }
  }

  function handleTransition(state: string) {
    if (state !== 'closed') {
      transition(state);
      return;
    }
    RNAlert.alert(
      'Close incident',
      'Select a closure reason',
      [
        ...CLOSURE_REASONS.map((reason) => ({
          text: humanize(reason),
          onPress: () => transition('closed', reason),
        })),
        { text: 'Cancel', style: 'cancel' as const },
      ],
    );
  }

  return (
    <ScrollView
      refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} tintColor={colors.muted} />}
      contentContainerStyle={styles.scrollContent}
    >
      {incident.description ? (
        <>
          <SectionHeader title="Description" />
          <Card>
            <Text style={styles.body}>{incident.description}</Text>
          </Card>
        </>
      ) : null}

      <SectionHeader title="Details" />
      <Card>
        <KeyValue label="Assignee" value={incident.assignee_username ?? 'Unassigned'} />
        <KeyValue label="Subject" value={incident.subject_name} />
        <KeyValue label="Source" value={humanize(incident.source_kind)} />
        <KeyValue label="TLP / PAP" value={`${incident.tlp} / ${incident.pap}`} />
        <KeyValue label="Created" value={formatDateTime(incident.created_at)} />
        <KeyValue label="Updated" value={formatDateTime(incident.updated_at)} />
        {incident.closure_reason ? (
          <KeyValue label="Closure reason" value={humanize(incident.closure_reason)} />
        ) : null}
        <KeyValue label="Linked alerts" value={incident.linked_alert_count} />
      </Card>

      {incident.iocs?.length ? (
        <>
          <SectionHeader title="IOCs" />
          <Card>
            {incident.iocs.map((ioc) => (
              <KeyValue key={ioc.id} label={humanize(ioc.kind)} value={ioc.value} />
            ))}
          </Card>
        </>
      ) : null}

      {incident.assets?.length ? (
        <>
          <SectionHeader title="Linked assets" />
          <Card>
            {incident.assets.map((link) => (
              <KeyValue key={link.id} label={link.asset?.kind ?? 'asset'} value={link.asset?.name} />
            ))}
          </Card>
        </>
      ) : null}

      <SectionHeader title="Actions" />
      <View style={styles.actions}>
        {allowedTransitions(incident.state).map((state) => (
          <Button
            key={state}
            title={humanize(state)}
            variant={state === 'closed' ? 'destructive' : 'secondary'}
            loading={transitioning === state}
            onPress={() => handleTransition(state)}
            style={styles.actionButton}
          />
        ))}
      </View>
    </ScrollView>
  );
}

function CommentsTab({ displayId }: { displayId: string }) {
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [draft, setDraft] = useState('');
  const [posting, setPosting] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api.get(`/api/incidents/${displayId}/comments/`);
      setComments(res.data);
    } catch {
      setComments([]);
    }
  }, [displayId]);

  useEffect(() => {
    load();
  }, [load]);

  async function postComment() {
    const body = draft.trim();
    if (!body) return;
    setPosting(true);
    try {
      await api.post(`/api/incidents/${displayId}/comments/`, { body, is_internal: true });
      setDraft('');
      await load();
    } catch (err: any) {
      RNAlert.alert('Could not post comment', err?.response?.data?.detail ?? 'Please try again.');
    } finally {
      setPosting(false);
    }
  }

  if (comments === null) return <LoadingView />;

  return (
    <View style={styles.commentsWrapper}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {comments.length === 0 && (
          <Text style={styles.emptyInline}>No comments yet.</Text>
        )}
        {comments.map((comment) => (
          <Card key={comment.id}>
            <View style={styles.commentHeader}>
              <Text style={styles.commentAuthor}>
                {comment.author_username ?? 'system'}
                {comment.is_internal ? '  ·  internal' : ''}
              </Text>
              <Text style={styles.time}>{timeAgo(comment.created_at)}</Text>
            </View>
            <Text style={styles.body}>{comment.deleted_at ? '(deleted)' : comment.body}</Text>
          </Card>
        ))}
      </ScrollView>
      <View style={styles.composer}>
        <TextInput
          style={styles.composerInput}
          placeholder="Add an internal comment…"
          placeholderTextColor={colors.muted}
          value={draft}
          onChangeText={setDraft}
          multiline
          testID="comment-input"
        />
        <Pressable
          onPress={postComment}
          disabled={posting || !draft.trim()}
          style={[styles.sendButton, (posting || !draft.trim()) && { opacity: 0.5 }]}
          accessibilityLabel="Send comment"
          testID="send-comment"
        >
          <Send size={18} color="#fff" />
        </Pressable>
      </View>
    </View>
  );
}

function TasksTab({ displayId }: { displayId: string }) {
  const [tasks, setTasks] = useState<IncidentTask[] | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.get(`/api/incidents/${displayId}/tasks/`);
      setTasks(res.data);
    } catch {
      setTasks([]);
    }
  }, [displayId]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleTask(task: IncidentTask) {
    const nextState = task.state === 'done' ? 'todo' : 'done';
    try {
      await api.patch(`/api/tasks/${task.id}/`, { state: nextState });
      await load();
    } catch (err: any) {
      RNAlert.alert('Could not update task', err?.response?.data?.detail ?? 'Please try again.');
    }
  }

  if (tasks === null) return <LoadingView />;

  return (
    <ScrollView contentContainerStyle={styles.scrollContent}>
      {tasks.length === 0 && <Text style={styles.emptyInline}>No tasks on this incident.</Text>}
      {tasks
        .slice()
        .sort((a, b) => a.display_order - b.display_order)
        .map((task) => (
          <Card key={task.id} onPress={() => toggleTask(task)} testID={`task-${task.id}`}>
            <View style={styles.taskRow}>
              {task.state === 'done' ? (
                <CheckCircle2 size={20} color={colors.success} />
              ) : (
                <Circle size={20} color={colors.muted} />
              )}
              <View style={styles.taskBody}>
                <Text
                  style={[styles.body, task.state === 'done' && styles.taskDone]}
                  numberOfLines={2}
                >
                  {task.title}
                </Text>
                {task.assignee_username ? (
                  <Text style={styles.time}>@{task.assignee_username}</Text>
                ) : null}
              </View>
              <Badge label={task.state} color={stateColor(task.state)} />
            </View>
          </Card>
        ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
  },
  title: {
    color: colors.foreground,
    fontSize: fontSize.lg,
    fontWeight: '700',
    marginBottom: spacing.sm,
  },
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  scrollContent: {
    paddingBottom: spacing.xl,
  },
  body: {
    color: colors.foreground,
    fontSize: fontSize.sm,
    lineHeight: 20,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  actionButton: {
    flexGrow: 1,
    minWidth: '45%',
  },
  commentsWrapper: {
    flex: 1,
  },
  commentHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  commentAuthor: {
    color: colors.primary,
    fontSize: fontSize.xs,
    fontWeight: '600',
  },
  time: {
    color: colors.muted,
    fontSize: fontSize.xs,
  },
  emptyInline: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    marginTop: spacing.xl,
  },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: spacing.sm,
    padding: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.card,
  },
  composerInput: {
    flex: 1,
    color: colors.foreground,
    fontSize: fontSize.md,
    backgroundColor: colors.secondary,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius,
    paddingHorizontal: spacing.md,
    paddingTop: 10,
    paddingBottom: 10,
    maxHeight: 120,
  },
  sendButton: {
    width: 46,
    height: 42,
    borderRadius: radius,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  taskRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  taskBody: {
    flex: 1,
  },
  taskDone: {
    textDecorationLine: 'line-through',
    color: colors.muted,
  },
});
