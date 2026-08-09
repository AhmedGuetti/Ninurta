import React, { useEffect, useState } from 'react';
import { Box, Text } from 'ink';
import { Banner } from '../components/Banner.jsx';
import { InputPrompt } from '../components/InputPrompt.jsx';
import { useMainApp } from './useMainApp.js';
import { turnStore } from './turnStore.js';

export function App() {
    const { started, sendMessage, runCommand } = useMainApp();
    const [messages, setMessages] = useState(turnStore.messages);
    const [activeTurn, setActiveTurn] = useState(turnStore.activeTurn);
    const [step, setStep] = useState(turnStore.step);

    useEffect(() => {
        const updateState = () => {
            setMessages([...turnStore.messages]);
            setActiveTurn(turnStore.activeTurn);
            setStep(turnStore.step);
        };
        turnStore.on('update', updateState);
        return () => turnStore.off('update', updateState);
    }, []);

    const handleSubmit = (text) => {
        if (text.startsWith('/')) {
            const [cmd, ...args] = text.split(' ');
            runCommand(cmd, args);
        } else {
            sendMessage(text);
        }
    };

    return (
        <Box flexDirection="column" padding={1}>
            <Banner />
            
            <Box flexDirection="column" marginBottom={1}>
                {messages.map((m, i) => (
                    <Box key={i} flexDirection="row">
                        <Text color={m.role === 'user' ? '#a21caf' : '#d946ef'} bold>
                            {m.role === 'user' ? 'User: ' : 'Ninurta: '}
                        </Text>
                        <Text>{m.content}</Text>
                    </Box>
                ))}
                
                {activeTurn && (
                    <Box flexDirection="column">
                        <Text color="#a78bfa" italic>{step ? `[${step}] ` : ''}</Text>
                        <Box flexDirection="row">
                            <Text color="#d946ef" bold>Ninurta: </Text>
                            <Text>{activeTurn}</Text>
                        </Box>
                    </Box>
                )}
            </Box>

            <InputPrompt onSubmit={handleSubmit} />
        </Box>
    );
}
