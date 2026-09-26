package cn.edu.bupt.youxueban;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.os.Build;
import org.json.*;
import java.util.HashSet;
import java.util.Set;

/** A persisted queue with one outstanding alarm, independent of either WebView. */
public final class ReminderReceiver extends BroadcastReceiver {
    private static final String STORE = "scheduled-reminders";
    private static final String ACTION = "cn.edu.bupt.youxueban.REMIND";

    private static PendingIntent alarmIntent(Context context) {
        return PendingIntent.getBroadcast(context, 0,
            new Intent(context, ReminderReceiver.class).setAction(ACTION).addFlags(Intent.FLAG_RECEIVER_FOREGROUND),
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    public static synchronized boolean replace(Context context, String json) {
        if (json == null || json.length() > 2_000_000) return false;
        try {
            JSONArray input = new JSONArray(json);
            if (input.length() > 10000) return false;
            JSONArray queue = new JSONArray();
            long now = System.currentTimeMillis();
            Set<String> delivered = context.getSharedPreferences(STORE, 0).getStringSet("delivered", Set.of());
            for (int i = 0; i < input.length(); i++) {
                JSONObject item = input.getJSONObject(i);
                long at = item.getLong("at");
                if (item.getString("id").length() > 160 || item.getString("title").length() > 80 ||
                    item.getString("body").length() > 1000 || at <= 0 || at > 253402300799000L) return false;
                if (at >= now && !delivered.contains(item.getString("id"))) queue.put(item);
            }
            if (!context.getSharedPreferences(STORE, 0).edit().putString("queue", queue.toString()).commit()) return false;
            schedule(context, queue);
            return true;
        } catch (Exception error) {
            android.util.Log.e("YouXueBan", "Reminder queue update failed: " + error.getClass().getSimpleName());
            return false;
        }
    }

    private static void schedule(Context context, JSONArray queue) throws JSONException {
        AlarmManager manager = context.getSystemService(AlarmManager.class);
        PendingIntent intent = alarmIntent(context);
        manager.cancel(intent);
        long next = Long.MAX_VALUE;
        for (int i = 0; i < queue.length(); i++) next = Math.min(next, queue.getJSONObject(i).getLong("at"));
        if (next == Long.MAX_VALUE) return;
        next = Math.max(System.currentTimeMillis() + 100, next);
        try {
            if (Build.VERSION.SDK_INT < 31 || manager.canScheduleExactAlarms()) {
                PendingIntent show = PendingIntent.getActivity(context, 0,
                    new Intent(context, MainActivity.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
                // These are explicit user-facing reminders, not background polling.
                // Alarm-clock delivery also survives OEM idle batching of ordinary alarms.
                manager.setAlarmClock(new AlarmManager.AlarmClockInfo(next, show), intent);
                return;
            }
        } catch (SecurityException ignored) { }
        manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, next, intent);
    }

    public static synchronized void restore(Context context) {
        try {
            JSONArray queue = new JSONArray(context.getSharedPreferences(STORE, 0).getString("queue", "[]"));
            JSONArray remaining = new JSONArray();
            long now = System.currentTimeMillis();
            for (int i = 0; i < queue.length(); i++) {
                JSONObject item = queue.getJSONObject(i);
                long at = item.getLong("at");
                if (at > now) remaining.put(item);
                else if (now - at < 86400000) deliver(context, item);
            }
            if (context.getSharedPreferences(STORE, 0).edit().putString("queue", remaining.toString()).commit())
                schedule(context, remaining);
        } catch (Exception error) {
            android.util.Log.e("YouXueBan", "Reminder delivery failed: " + error.getClass().getSimpleName());
        }
    }

    private static void deliver(Context context, JSONObject item) throws JSONException {
        SharedPreferences store = context.getSharedPreferences(STORE, 0);
        Set<String> delivered = new HashSet<>(store.getStringSet("delivered", Set.of()));
        String id = item.getString("id");
        if (delivered.contains(id)) return;
        if (Build.VERSION.SDK_INT >= 33 &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return;
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        String channelId = item.optBoolean("silent") ? "reminders-silent" : "reminders";
        NotificationChannel channel = new NotificationChannel(channelId, item.optBoolean("silent") ? "静音提醒" : "课程与任务提醒", NotificationManager.IMPORTANCE_DEFAULT);
        if (item.optBoolean("silent")) { channel.setSound(null, null); channel.enableVibration(false); }
        manager.createNotificationChannel(channel);
        PendingIntent open = PendingIntent.getActivity(context, 0, new Intent(context, MainActivity.class),
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notification = new Notification.Builder(context, channelId)
            .setSmallIcon(android.R.drawable.ic_popup_reminder).setContentTitle(item.getString("title"))
            .setContentText(item.getString("body")).setStyle(new Notification.BigTextStyle().bigText(item.getString("body")))
            .setContentIntent(open).setAutoCancel(true).build();
        manager.notify(id, 0, notification);
        if (delivered.size() >= 10000) delivered.remove(delivered.iterator().next());
        delivered.add(id);
        store.edit().putStringSet("delivered", delivered).commit();
    }

    @Override public void onReceive(Context context, Intent intent) {
        android.util.Log.i("YouXueBan", "Native reminder receiver invoked");
        restore(context);
    }
}
