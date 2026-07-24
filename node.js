const port = process.env.PORT || 8080;
// Explicitly bind to 0.0.0.0
app.listen(port, '0.0.0.0', () => {
  console.log(`Server listening on port ${port}`);
});
