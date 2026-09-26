# Complete RAG Pipeline Tutorial: Build a PDF Agent with Python, LangChain, & Groq

> Source: [StatLearn Tech — Complete RAG Pipeline Tutorial: Build a PDF Agent with Python, LangChain, & Groq](https://www.youtube.com/watch?v=g8FIfgKYtyI)

## TL;DR

- Builds a RAG (Retrieval-Augmented Generation) app: an AI agent that answers questions using a 34-page PDF about artificial intelligence.
- Stack: Python + LangChain, Groq as the free LLM provider, a free Hugging Face embedding model, and an in-memory vector store.
- Pipeline: load PDF → split into overlapping chunks → embed chunks as vectors → store → agent tool does similarity search (top 3) → LLM answers from that context.
- Uses `agent.stream(...)` to show every step: user message → tool call → tool result → final AI answer.

## Topics

### What RAG is

RAG lets an LLM answer from your own documents by first finding the relevant parts and adding them to the prompt.

- Goal: an agent that finds where in the PDF the answer lives and answers from it — [00:00](https://youtu.be/g8FIfgKYtyI?t=0)
- **Retrieval** = get information from the docs, **Augmented** = add that context to the LLM prompt, **Generation** = generate the answer from that context — [00:00](https://youtu.be/g8FIfgKYtyI?t=0)

### Tools & setup

- Groq is not an LLM itself — it's a provider hosting open-source LLMs; its API key is free — [01:04](https://youtu.be/g8FIfgKYtyI?t=64)
- Project folder needs 3 files: `.env`, the PDF, and a Python script (speaker uses `rag_1.py`) — [01:04](https://youtu.be/g8FIfgKYtyI?t=64)
- Each package's job: `langchain` core, `langchain-groq` for Groq, `langchain-huggingface` + `sentence-transformers` for embeddings, `pypdf` to read PDFs, `python-dotenv` to load env variables — [02:07](https://youtu.be/g8FIfgKYtyI?t=127)
- API key from `console.groq.com/keys` (log in with Gmail, click **Create API Key**) — [02:07](https://youtu.be/g8FIfgKYtyI?t=127)

### LLM model & reasoning format

- `ChatGroq` is the LLM; pass the actual model name since Groq is only a provider — [04:13](https://youtu.be/g8FIfgKYtyI?t=253)
- `reasoning_format="parsed"` moves the model's "thinking" into a separate field so the reply stays clean — [04:13](https://youtu.be/g8FIfgKYtyI?t=253)

### Chunking (splitting) the PDF

Big documents are split into small pieces so you don't overload the LLM's context.

- Chunk size = max characters per chunk — [06:18](https://youtu.be/g8FIfgKYtyI?t=378)
- Chunk overlap = characters shared between neighbouring chunks, so a sentence cut in half still keeps its meaning in one of them — [07:21](https://youtu.be/g8FIfgKYtyI?t=441)

### Embeddings & vector store

- Embedding = turning text into vectors (lists of numbers). Machines search numbers much more easily than text, so you can quickly find the most similar pieces — [08:24](https://youtu.be/g8FIfgKYtyI?t=504)
- Embedding model: Hugging Face `sentence-transformers/all-MiniLM-L6-v2` — free, has some token limit — [09:27](https://youtu.be/g8FIfgKYtyI?t=567)
- Vectors stored in a simple `InMemoryVectorStore` (any vector store would work) — [10:30](https://youtu.be/g8FIfgKYtyI?t=630)

### Agent, retrieval tool & streaming

- An agent = prompt + LLM model + set of tools — [10:30](https://youtu.be/g8FIfgKYtyI?t=630)
- The retrieval tool does a similarity search (top 3) and returns the results as one string with content + source — [11:32](https://youtu.be/g8FIfgKYtyI?t=692)
- The tool's docstring tells the agent what the tool does, so it knows when to call it — [15:45](https://youtu.be/g8FIfgKYtyI?t=945)
- Streaming with `stream_mode="values"` prints each step so you can see the RAG flow happen — [14:42](https://youtu.be/g8FIfgKYtyI?t=882)

### Running it & reading the output

- First run downloads the Hugging Face model (one-time only) — [16:47](https://youtu.be/g8FIfgKYtyI?t=1007)
- Output: Human message → AI message with tool call (`query: what is AI`) → Tool message with 3 contexts (k=3) → final AI answer from the document. Hugging Face tokenizer logs can be ignored — [17:50](https://youtu.be/g8FIfgKYtyI?t=1070)
- Try other queries — answers always come from your PDF — [17:50](https://youtu.be/g8FIfgKYtyI?t=1070)

## 🛠 Tutorials

### Tutorial: Build a RAG PDF question-answering agent

**Goal:** Make a Python agent that answers questions using the content of a PDF.
**You need:** Python, a free Groq API key, a PDF (speaker uses `ai.pdf`, 34 pages — link in video description), a folder with `.env`, the PDF and a script like `rag_1.py`.

> Code below is rebuilt from the narration (auto-captions said "Grok" — it's **Groq**). Check against the video if something errors.

1. **Install packages** — gets LangChain, the Groq connector, embedding tools, PDF reader and env loader. [01:04](https://youtu.be/g8FIfgKYtyI?t=64)
   ```bash
   pip install langchain langchain-groq langchain-huggingface sentence-transformers pypdf python-dotenv
   ```
   (Code later also imports `langchain_community` and `langchain_text_splitters` — install them if you get import errors.)
2. **Get a Groq API key** — needed to call Groq's models; it's free. Go to `console.groq.com/keys` → log in → **Create API Key**. [02:07](https://youtu.be/g8FIfgKYtyI?t=127)
3. **Create `.env`** — keeps your secret key out of the code; `ChatGroq` reads this name automatically. [03:09](https://youtu.be/g8FIfgKYtyI?t=189)
   ```
   GROQ_API_KEY=<your key>
   ```
4. **Load env variables** — makes the `.env` values available to your script. [03:09](https://youtu.be/g8FIfgKYtyI?t=189)
   ```python
   from dotenv import load_dotenv
   load_dotenv()
   ```
5. **Create the LLM** — this is the "brain" that writes answers. [04:13](https://youtu.be/g8FIfgKYtyI?t=253)
   ```python
   from langchain_groq import ChatGroq
   model = ChatGroq(model="qwen/qwen3-32b", reasoning_format="parsed")
   ```
   Model name heard as "12 3-32B" — most likely Qwen3-32B _(unclear in video)_.
6. **Load the PDF** — reads the pages into LangChain documents. Print a message first so users don't stare at a blank screen while it loads. [05:16](https://youtu.be/g8FIfgKYtyI?t=316)
   ```python
   from langchain_community.document_loaders import PyPDFLoader
   print("Loading PDF document...")
   loader = PyPDFLoader("ai.pdf")
   docs = loader.load()
   ```
7. **Split into chunks** — small overlapping pieces fit in the LLM's context and keep meaning across cuts. [06:18](https://youtu.be/g8FIfgKYtyI?t=378)
   ```python
   from langchain_text_splitters import RecursiveCharacterTextSplitter
   text_splitter = RecursiveCharacterTextSplitter(chunk_size=..., chunk_overlap=...)
   all_splits = text_splitter.split_documents(docs)
   ```
   Exact `chunk_size` / `chunk_overlap` values not said in captions (100 chars used only as an example).
8. **Create embeddings** — converts text chunks to vectors so they can be searched by meaning. [09:27](https://youtu.be/g8FIfgKYtyI?t=567)
   ```python
   from langchain_huggingface import HuggingFaceEmbeddings
   print("Building embeddings...")
   embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
   ```
9. **Build the vector store** — stores all chunk vectors in memory for fast similarity search. [10:30](https://youtu.be/g8FIfgKYtyI?t=630)
   ```python
   from langchain_core.vectorstores import InMemoryVectorStore
   vector_store = InMemoryVectorStore.from_documents(all_splits, embeddings)
   ```
10. **Write the retrieval tool** — the agent calls this to fetch the 3 most relevant chunks; the docstring tells the agent what it does. [11:32](https://youtu.be/g8FIfgKYtyI?t=692)

    ```python
    from langchain_core.tools import tool

    @tool
    def retrieve_context(query: str):
        """Retrieves relevant context from the PDF document based on the query."""
        similar_docs = vector_store.similarity_search(query, k=3)
        data = []
        for doc in similar_docs:
            data.append(f"""Content: {doc.page_content}
    Source: {doc.metadata.get("source", "unknown")}""")
        return "\n\n".join(data)
    ```

11. **Create the agent** — ties model + tool + system prompt together. [13:38](https://youtu.be/g8FIfgKYtyI?t=818)
    ```python
    from langchain.agents import create_agent
    prompt = "You are an agent who retrieves context from PDF doc."
    agent = create_agent(model, tools=[retrieve_context], system_prompt=prompt)
    ```
12. **Ask a question and stream steps** — `stream_mode="values"` returns state after each step, so you see tool call → context → answer. [14:42](https://youtu.be/g8FIfgKYtyI?t=882)
    ```python
    query = "What is AI according to the document?"
    for step in agent.stream(
        {"messages": [{"role": "user", "content": query}]},
        stream_mode="values",
    ):
        step["messages"][-1].pretty_print()
    ```
    (Simpler alternative mentioned: `agent.invoke(...)` returns only the final response.)
13. **Run it** — expect "Loading PDF document", "Building embeddings", then the message steps. [16:47](https://youtu.be/g8FIfgKYtyI?t=1007)

**Watch out for:**

- Tool must return a **string** — speaker first appended dicts to `data`, which breaks `"\n\n".join(data)`; fixed by using an f-string. [15:45](https://youtu.be/g8FIfgKYtyI?t=945)
- `ChatGroq` first argument must be passed as `model=...`. [05:16](https://youtu.be/g8FIfgKYtyI?t=316)
- Forgetting the `@tool` decorator or docstring → agent can't use/understand the tool. [12:35](https://youtu.be/g8FIfgKYtyI?t=755)
- First run is slow (embedding model download); later runs aren't. [16:47](https://youtu.be/g8FIfgKYtyI?t=1007)
- Env key name must match what `ChatGroq` expects (`GROQ_API_KEY`). [03:09](https://youtu.be/g8FIfgKYtyI?t=189)

## Key Takeaways

- RAG = retrieve relevant chunks → add them to the prompt → generate an answer.
- Chunk overlap keeps meaning intact across chunk boundaries.
- Embeddings turn text into vectors so "most similar" search is fast and meaningful.
- In an agent, the tool's docstring is its instruction manual for the LLM.
- Streaming the agent is a great way to see (and debug) what RAG does step by step.

## Related

- [[RAG]]
- [[LangChain]]
- [[AI Agents]]
- [[Embeddings]]
- [[Vector Databases]]
- [[Python]]
- [[AI]]

> [!note]- Full transcript (cleaned)
> **[00:00]** Hey everyone, how are you? In this video, I'm going to tell you how to create a rag application using Python and LangChain. So, basically what I have is a PDF file and in this PDF file, I have a detail about what exactly is artificial intelligence and this PDF file is around 34 pages. So, it has a lot of details about what exactly is artificial intelligence. What I want to create is I want to create a application which is basically an AI agent which can answer the questions of this PDF. If I ask what exactly is AI or artificial intelligence, it should know that, okay, where is the exact details in this particular doc and get that details and provide me the answer. So, that's basically what exactly is a rag. Rag stands for retrieval, augmented, and generation. This retrieval means getting some information, augmented means adding some extra context to already existing information, and generation means generating some data. So, we are going to retrieve the documents or details from the PDF, augment our LLM prompt or query with that context, and generate the answer based on that particular context. So,
>
> **[01:04]** that's what we need to achieve and that's basically rag is all about. We are going to make use of the Grok LLM and basically Grok is not an LLM, it's an LLM provider which hosts different open-source LLMs. So, we are going to make use of this because the API key is free and we are going to make use of Python and LangChain. So, first of all, we need to import the required or I would say install the required module. So, just go to your terminal and before you run that installation command, I would tell you that create a folder in which you should have three files. One of the files should be .env file. I will tell you what the content of it will be. Another file will be the PDF file which you will perform rag on and it should It is not required to be the same file, but I would highly recommend you to get the same file and you can get the link of this file in the description of this video. Also, you need to create a Python code. Name your code or file anything. I have named it as rag_1.py. So, let's first install the required modules. So, you just need to run a command and the command is pip install LangChain, LangChain Grok, LangChain Hugging Face, sentence transformer,
>
> **[02:07]** PyPDF, python. env. So, this LangChain is for the core LangChain functionality. LangChain Grok is to use the Grok LLM provider. LangChain Hugging Face is to use the Hugging Face embedding model and the embedding transformer which we are going to use in the sentence transformers. PyPDF is to load your Python file and python. env is to load your environment variables. Now, what exactly is embedding? I will tell you while I will write the embedding code. So, don't worry about anything. You can find this pip command in the description of this video as well. Run the command. For me, all the modules are already installed. For you, it will take like few seconds and it will also get installed. Once the installation is done, I will just clear the console and actually close the terminal and start writing our code. So, first of all, we need the Grok API key to access the Grok models, right? So, you can get actually get the API key from a website called as console.grok.com/keys and you can find the link of this website in the description of this video. You can log in to this particular portal using your Gmail account. So, you can get the key very easily. Just click on this create API key button.
>
> **[03:09]** And it's free, guys. So, you don't need to worry about any kind of cost. Now, let's get back to our coding environment and let's start writing our code. So, let's talk about the .env file. In this file, you will have one line of code and there will be a key which will be available in your code as a environment variable and the key name is grok_api_key and the value is going to be the API key which you just got from the console.grok.com. Create this file and you should have the ai.pdf file or any other file as a PDF in the same folder and you should have your Python file. So, first of all, we need to load the .env file as environment variables. So, we are actually going to make use of from .env. Let's import something called as dot load.env and call the function load.env. This will make sure that all the details in your .env file are actually available as a system or environment variable in your code. The LLM model, the Groq LLM model, requires the key named as Groq API key. So, it will automatically be loaded. And next is we need to load or import from LangChain {underscore} Groq, we need to
>
> **[04:13]** import something called as ChatGroq. That will be our LLM model. So, we can say model will be equal to ChatGroq model. And basically, this is a model provider, so we need to provide the actual model name. And we are going to make use of 12 models. And the actual model name will be 12 3-32B. And also, we are going to make use of another parameter called as the reasoning format, which will be equal to past. Now, the value of reasoning format equal to past means it is going to separate the reasoning into a dedicated field while keeping the response concise. So, many a time you might have seen that when you ask something from, let's say, ChatGPT or Google Gemini, it shows some thinking part before responding you with the actual data. So, that thinking part is something which will be separated out in another attribute when you say the reasoning format is past. Because we are actually interested in the actual response. We are not interested in the reasoning or the thinking part. So, once we have the model created, now we are going to load our PDF file. So, to load our PDF file, we are going to make use of a class called as PyPDFLoader. And this is actually available in LangChain community module.
>
> **[05:16]** So, we can say from LangChain {underscore} community {dot} document_loaders, we need to import something called as PyPDFLoader. And let's assign this a variable. So, loader is equal to PyPDFLoader. And the file name is going to be ai.pdf. That's my file name. You need to write whatever is your file name path. Now, the next is once we have the loader ready, let's actually load the data and assign this in a variable called as docs. So, this will be loader.load. So, our data is now loaded into the variable called as docs. And also, in this model equal to chat group line, this first argument is actually your model. So, we need to say model equal to our model name. So, we need to provide these two arguments. Now, let's continue. So, now that our PDF data is loaded, let's us also write a simple print message that loading the PDF document. Well, what happens is when you are loading your document, it takes some time and your user, if they are using your terminal, can actually just see a empty screen. So, you want to avoid this and tell them that PDF data is being loaded so that they knows that they have to wait. Now, next is we need to create the
>
> **[06:18]** splitter. Basically, we need to split our PDF data into chunks because if you see right now we have a 34 pages PDF. Tomorrow we can have a 3400 pages PDF, right? So, your PDF size can be huge. So, you don't want to load the whole data in your memory at the same time. That can just overload the context of your LLM. So, you want to avoid it and you just want to load the data in chunks. So, for that we need to split our data. And to split our data, we are actually make going to make use of something called as recursive character text splitter, which is a part of LangChain text splitter module. So, let's actually import it. So, we can say from LangChain_text_splitters, we need to import a recursive text splitter. This will split your text recursively into chunks. So, let's actually make use of this and create a text splitter. So, we can say text splitter equal to recursive character text splitter and it needs two arguments. It needs the chunk size and chunk overlap. Basically, the chunk size is the maximum characters in a single chunk and chunk overlap is actually a very interesting data. It's the amount
>
> **[07:21]** of characters which can overlap in two continuous chunks. What I want to say here is let's say you want to create the chunks of this particular PDF data. Now, here if you notice the data is too big, right? We need to create a chunk of 100 characters. And let's say these are 100 characters. Now, the problem is if you have a one chunk which is this one what's highlighted right now, it doesn't hold a complete meaning, right? So, what happens is if this is your first chunk and this is your second chunk, they the both the chunks doesn't hold a complete meaning. So, we have something called a chunk overlap, which says that if you have a first chunk, let's say something like this, then the second chunk can actually overlap and start in between the first chunk. So, what I'm That is, your first chunk can be this one from in simple terms to conclusions, and your second chunk can actually start from thoughts and even draw conclusions, it should be able to correct itself. So, the two chunks, the two continuous chunks have some data in common, which gives them a complete a continuous meaning. Right? So, that's why we have something called a chunk overlap. How many characters can actually overlap at the
>
> **[08:24]** end of first chunk and the at the and at the start of the second chunk. So, now once we have the text splitter ready, we will create a splits. So, we will save all splits or all chunks, you can say, is equal to text splitter. start split docs. Split documents, and in this you will pass your documents. So, once you have all the splits or all the chunks ready, we can start our embedding process. Now, what is this embedding? So, basically your PDF data is a text data, right? Now, this text data is something which is hard for a model to understand compared to numbers. So, the text is converted into numbers and these numbers are converted into vectors. So, this is the process of embedding your data. You are embedding your data ultimately to a vector, which is ultimately a number. And these numbers are easy to understand for a model and easy to search. So, you're basically storing your text data as a vector data. So, from a vector data, we can easily find what's the most similar data in your whole database. Finding it in a text is going to be difficult. For a human being, it might be easy. For a machine, it the vector part is easy. So, that's the embedding
>
> **[09:27]** process in short. Embedding is actually a very complex process, but in short, that's what embedding is all about, converting your text into vector data. So, let's do it. We need to have a embedding model. So, let's actually create a embedding model so we can say embeddings will be equal to and we are going to make use of hugging face embedding model which is available to us freely. So, let's make use of this. Before using it, we need to import it. So, we can say from LangChain {underscore} hugging face, we need to import hugging face embedding model and then create the embedding. So, embedding will be equal to hugging face embedding and the model name will be sentence transformers {slash} all mini LM L6 V2. That's the model or that's a transformer which will be acting as our embedding model and this is provided by hugging face. And this is free as well. You can use it freely. It does have some token limit, but that's fine. We can use it for now. Next is we need to create a vector store and before actually I do it, embedding can also take some time. So, let's have a simple print message building embeddings. So, before starting to build the embeddings, we will have this message. Next is since our embedding instance is ready, we will do
>
> **[10:30]** the embedding on our actual data, the all splits data using a vector store. We will store our embedding as a vector in a vector store and this vector store can be any valid vector store, but right now we are going to make use of a simple in-memory vector store. So, for that we need to import so we can say from LangChain core {dot} vector stores, we need to import something called as in-memory vector store and let's make an instance of this as well. So, after embedding, let's create our vector store and this will be equal to in-memory vector store {dot} from documents. So, we have the documents, right? We have all the splits. And this is our embedding. So, this will be our code for storing our data as a vector. So, once our vector store is ready, we can actually create a tool for our agent. We are actually going to create an agent which will have some prompt, some LLM model. We have We already have the model. We will create our prompt. So, we will have a prompt, an LLM model and some set of tools. So, we will create a tool which is going to fetch the relevant information from the vector store based on the query. So, let's create that tool. So, let's name that tool as and we will create a function tool so I'm using def. So, name the tool
>
> **[11:32]** as def retrieve {underscore} context from a given query, which is going to be a string. And inside this, first of all, we are going to do a similarity search for the given query. So, we will say similar docs is equal to vector store {dot} similarity search based on this query and give me the top three similar data. So, whatever is going to be your query, let's say we queried at what is AI. So, based on that particular query, it will do a query similarity search in our vector store and find the top three similar data and return us an array. So, let's combine this array, which is actually inside the similar docs. Let's combine the array like as a string because we will give this a string directly to our LLM model. So, let's create our data, which is going to be a list for now. Inside this list, we are going to store the different details which we are going to get from our docs. So, for that, what we have done is we have run a loop for doc in similar docs, data {dot} append. We are appending the data and we are appending the content and metadata. The content we are going to get is from the doc {dot} page content and the metadata
>
> **[12:35]** we will get from the doc {dot} metadata. And we actually don't need all the metadata, so let's actually just give the source and this will be doc {dot} metadata. Let's get the source and if the source is not there, just return unknown. Now, let's return back this data, the data which we just created as a string, so I can say return {dot} join data. Now, let's separate the data or the different contexts using two line changes. So, now what we have is we have a function which will act as a tool which is going to search the similar information from the vector store based on the query and return back us a string. And also, we need to add a decorator named as {at} tool. I mean, we need to import this tool decorator, which is available in the LangChain module. So, just add this particular decorator. This is going to make sure that this will now act as a tool, this function. And let's actually import this as well, so we can say from LangChain core {dot} tools import something called as tools. So, once this is done, we are good. We are good with our retrieval tool as well. Next is we need to create our agent, right? Now, we can create our actual AI agent.
>
> **[13:38]** So, we can say agent is equal to create underscore agent. We need to import this create agent. So, we can say from LangChain dot agents import something called as create agent. In this create agent, we need to pass what's the model which we need to use as the first argument. What are the different set of tools which we have? So, we have just one tool, which is the retrieve context. So, that's the tool which we will have. And we need to pass the system prompt as well, the initial system prompt. We are going to have a system prompt. So, let's say this is equal to prompt. We will create the variable. We will create this variable prompt. We will write our prompt. So, our agent is ready. Next is we need a query or a question. So, let's have a question. What is AI according to the document? Let's have a simple straightforward question, and we need the answer. Now, to invoke this model, we can actually invoke it directly by saying that agent dot invoke and get the response. But, that's not what I want to do. I want to show you what's happening step-by-step. How this agent will call the tool, get the context, then based on the context, it will call the LLM again with some added
>
> **[14:42]** or augmented data, and then it will generate the data based on the extra context. So, what I will make use of is stream. I will stream the whole process of agent calling the LLM model. So, I will say for step in agent dot stream. We are going to stream our agent, and in this we need to pass the initial message or our query, and we need to pass something called as stream mode. This will be equal to values. What this will do is after every step, we will get back the data or the response. So, we can print it. So, we can say step, then messages. We will get some messages, and we need the latest message. So, we will say minus one because we will get it as a list. So, the minus one index will give us the latest information dot pretty underscore print. So, this will print it in a pretty good way. Also, let's add our agent stream initial message. So, this will be passed as a key named as messages and the value will be a list. The list will have just one value, which is actually going to be a dictionary. In this dictionary, we are going to pass two data, the role who is sending the message and the actual
>
> **[15:45]** query. So, we can say the content will be the query and the role will be the user. Now, finally, we are on the prompt side. Let's make use of the prompt and say that you are an agent who retrieves context from PDF doc. That's a very simple system prompt. Now, before we run the code, in the tool, we actually need to add a docstring, which is going to act as a documentation of your tool. So, let's add a docstring at the start and let's write it as "Retrieves relevant context from the PDF document based on the query." Well, this is the docstring which helps the agent or the model realize what this tool what this tool is going to do and based on it, it will call the tool with the relevant information. So, I think our code is ready, but I think there's one place where we have done a small mistake, which is data.append. In the tool, we have this data.append and we are appending a dictionary, which we should not because later on we are joining the data. So, we should have it as a string, so let's make it as a string. So, I'll just convert this to
>
> **[16:47]** a string and since I'm using multi-lines, I'll just use the triple quotes. So, triple quotes here as well. And use the string formatting. So, what I will have is I'll have the content and this will be my content, which will go inside the curly braces. Right? And similarly for the source as well, I'll have the source, which will go inside the curly braces. So, our string formatting is going to work. So, basically, every doc data will be appended as a string and later on, since we have it inside a list, I'll convert it back to a string again. Now, we should be good to run the code. So, let's just run the code and let's see what the response we are getting. If you're running it for the first time, it will take some time because it will also download the hugging face embedding model, basically the sentence transformer which we are using. But, this will be a one-time process. Every subsequent runs will not download the model again. So, it's just a one-time process. So, you can see we have the loading PDF document now. Then, we are building the embeddings and then we are finally getting the response. So, just see the response. We have a human message which is our query, what is AI according to the document,
>
> **[17:50]** and we have some other logs coming from the hugging face tokenizer, which you can ignore for now. Then, we have a AI message that there is a tool calling done with a query, what is AI? Then, the tool message response with some data. It has this It has the content which is the artificial intelligence coming from the page number one and some definition and another content and I think it will have another content. Total three contents are here. And then, the final AI message which is about what exactly is AI according to this document. This is the definition of AI according to the document. So, we are basically doing rag here. If you see the code right now, we are using the value of k equal to three and that's why we got three different contexts coming from the doc or the vector store. And finally, we got the answer of our query. The query was, what is AI according to the document, right? You can see it on the line number 38. So, this is how you create a rag. What I will ask you guys is, try to change the query and see what's the response you are getting. And every time you will see a different response based on the different query and the response will actually be coming from your actual PDF file.
>
> **[18:53]** But, if you face any error which I believe you can or anyone can if they are building a rag app for the first time, then make sure that you put it in the comment box. This is a one-time process, guys. I will tell you. Once you understand the basics of rag, once you understand how it actually works under the hood, creating bigger complex application will be a piece of cake for you guys. And if you face any issues, you know where to come, right? You can just comment it out in this video and I will provide the solution for it. So guys, that's it for this video. I hope this video has explained you something about rag, embedding, and creating a whole code of rag. And if it did, then make sure that you hit that like button. And guys, honestly, it took a lot of efforts to create this video. So make sure that you subscribe to the channel as well if you found this video helpful. I will see you guys in the next video. Thank you for watching this one.
