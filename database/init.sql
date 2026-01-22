-- TaggerNews Database Schema
-- 🧠 Human-Written: SQL Triggers for data integrity

-- Stories table
CREATE TABLE IF NOT EXISTS stories (
    id SERIAL PRIMARY KEY,
    hn_id INTEGER UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    url VARCHAR(2000),
    score INTEGER DEFAULT 0,
    author VARCHAR(100) NOT NULL,
    comment_count INTEGER DEFAULT 0,
    hn_created_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Summaries table
CREATE TABLE IF NOT EXISTS summaries (
    id SERIAL PRIMARY KEY,
    story_id INTEGER UNIQUE NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    model VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_stories_hn_id ON stories(hn_id);
CREATE INDEX IF NOT EXISTS idx_stories_score ON stories(score DESC);
CREATE INDEX IF NOT EXISTS idx_stories_created_at ON stories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_summaries_story_id ON summaries(story_id);

-- 🧠 Human-Written: Trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_stories_updated_at
    BEFORE UPDATE ON stories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 🧠 Human-Written: Trigger to validate score is non-negative
CREATE OR REPLACE FUNCTION validate_score()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.score < 0 THEN
        NEW.score = 0;
    END IF;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER validate_story_score
    BEFORE INSERT OR UPDATE ON stories
    FOR EACH ROW
    EXECUTE FUNCTION validate_score();
