-- The thread an ask serves (design threads.md section 3, communication-protocols.md
-- section 7.5): an agent asking on behalf of a thread it takes part in names that thread
-- with `serves` on its send, and the link is kept on the thread the ask opens. The
-- links form a tree of threads across lines; ending a thread ends no other.
ALTER TABLE threads ADD COLUMN serves uuid REFERENCES threads(id);
