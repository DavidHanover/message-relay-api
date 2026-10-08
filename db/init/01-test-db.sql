-- Separate database for the pytest suite so tests never touch dev data.
CREATE DATABASE messaging_test OWNER messaging;
