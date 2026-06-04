import { useState } from "react";
import axios from "axios";

export default function Upload() {

  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useState("");

  const upload = async () => {

    const form = new FormData();
    form.append("file", file);

    const res = await axios.post(
      "http://localhost:8000/upload",
      form
    );

    setJobId(res.data.job_id);
  };

  return (
    <div>
      <input type="file" onChange={e => setFile(e.target.files[0])} />
      <button onClick={upload}>Upload</button>

      {jobId && <p>Job ID: {jobId}</p>}
    </div>
  );
}