-- Today's list needs to show *when* each item is due, not just why it's there - the
-- date was already tracked on follow_ups.due_date but never carried into the
-- daily_priority snapshot alongside the reason text it's already copying.
ALTER TABLE daily_priority ADD COLUMN due_date date;
